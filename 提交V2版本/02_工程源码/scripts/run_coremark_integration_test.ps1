param(
    [string]$ToolchainRoot = '',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [ValidateSet('14.2.0','16.2.0')][string]$ExpectedGccVersion = '16.2.0',
    [ValidateSet('O2','O3')][string]$CoreMarkOptimization = 'O2',
    [ValidateSet('performance','validation','both')][string]$Mode = 'both',
    [ValidateSet('compact','bootloader')][string]$WorkloadLayout = 'compact',
    [string]$CapacityEvidence = '',
    [ValidatePattern('^$|^[0-9a-fA-F]{64}$')][string]$ExpectedRomSha256 = '',
    [ValidateRange(30,1200)][int]$TimeoutSeconds = 600,
    [ValidateRange(1,2)][int]$BuildJobs = 2
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
. (Join-Path $PSScriptRoot 'compiler_capacity_helpers.ps1')
$originalPath = $env:PATH
try {
    if ($ExpectedRomSha256 -and $Mode -eq 'both') { throw 'A same-ROM comparison must select one seed mode.' }
    # Explicit candidate selection is local to this test; production stays fixed.
    $CpuGccVersion = $ExpectedGccVersion
    $toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
    $capacity = $null
    if ($CapacityEvidence) {
        if ($WorkloadLayout -ne 'bootloader') { throw 'CapacityEvidence requires WorkloadLayout bootloader.' }
        $CapacityEvidence = [IO.Path]::GetFullPath($CapacityEvidence)
        $capacity = Read-CompilerCapacityEvidence -Path $CapacityEvidence -Root $root -Toolchain $toolchain -Optimization $CoreMarkOptimization
    } elseif ($WorkloadLayout -eq 'bootloader' -and ($ExpectedGccVersion -ne '14.2.0' -or $CoreMarkOptimization -ne 'O2')) {
        throw 'Only the historical GCC14/O2 layout has a fixed address. Other candidates require passing CapacityEvidence.'
    }
    & (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
    $core = Join-Path $root 'sw/coremark'
    Assert-CpuCoremarkSources -Directory $core
    $suffix = if ($WorkloadLayout -eq 'bootloader') { '-bootlayout' } else { '' }
    if ($capacity) { $suffix += '-map' + $capacity.map_sha256.Substring(0,8) }
    $cpuHash = (Get-FileHash -LiteralPath (Join-Path $root 'rtl/cpu/CoreTop.sv') -Algorithm SHA256).Hash.ToLowerInvariant()
    $suffix += '-cpu' + $cpuHash.Substring(0,8)
    $out = Join-Path $root "artifacts/selftest/coremark_short/gcc$ExpectedGccVersion-$CoreMarkOptimization$suffix"
    $linker = if ($WorkloadLayout -eq 'bootloader') { 'sim/coremark_short/boot_layout.ld' } else { 'sw/bootloader/link.ld' }
    $modes = if ($Mode -eq 'both') { @('performance','validation') } else { @($Mode) }
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $linkerPath = Join-Path $root $linker
    if ($capacity) {
        $linkerText = [IO.File]::ReadAllText($linkerPath)
        if ([regex]::Matches($linkerText,'0x1c01b0a8').Count -ne 2) { throw 'Review changed bootloader-layout template before adapting its work address.' }
        $linkerText = $linkerText.Replace('0x1c01b0a8',$capacity.static_memblk)
        $linkerText = $linkerText.Replace('current complete GCC14/O2 bootloader','full candidate bootloader selected by capacity evidence')
        $linkerPath = Join-Path $out 'candidate_layout.ld'
        [IO.File]::WriteAllText($linkerPath,$linkerText,[Text.UTF8Encoding]::new($false))
    }
    $linkerHash = (Get-FileHash -LiteralPath $linkerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $rtl = @('rtl/cpu/CoreTop.sv','rtl/clint.v','rtl/cpu_top.v',
        'rtl/soc/axi_1x2.v','rtl/soc/axi_boot_periph.v','rtl/soc/axi_cpu_sys_cdc.v','rtl/soc/uart_tx_fifo.v',
        'sim/tb_cpu_integration.sv')
    $coreSources = @('core_main.c','core_list_join.c','core_matrix.c','core_state.c','core_util.c','core_portme.c')
    $inputs = $rtl + @('sw/bootloader/start.S',$linker,'sw/bootloader/runtime.c',
        'sw/bootloader/soc.h','sim/coremark_short/main.c','scripts/run_coremark_integration_test.ps1',
        'scripts/check_coremark_short.ps1','scripts/riscv_toolchain.ps1','scripts/simulation_tools.ps1',
        'scripts/bounded_process.cs','scripts/bin_to_hex.ps1','scripts/compiler_capacity_helpers.ps1','sw/coremark/core_portme.h',
        'sw/coremark/coremark.h','sw/coremark/upstream.json') + @($coreSources | ForEach-Object { 'sw/coremark/' + $_ })
    $hashes = [ordered]@{}
    foreach ($name in $inputs) { $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
    $common = @('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany',
        '-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin',
        '-fno-common','-ffunction-sections','-fdata-sections','-Wall','-Wextra')
    foreach ($seedMode in $modes) {
        $directory = Join-Path $out $seedMode
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        $validation = if ($seedMode -eq 'validation') { 1 } else { 0 }
        $definitions = @('-DITERATIONS=10',"-DVALIDATION_RUN=$validation")
        $config = Join-Path $directory 'test_build_config.h'
        $configText = '#define COMPILER_FLAGS "-' + $CoreMarkOptimization + ' -march=' + $CpuMarch + ' -mabi=' + $CpuAbi + '"'
        [IO.File]::WriteAllText($config, $configText + "`n", [Text.UTF8Encoding]::new($false))
        $objects = @()
        foreach ($name in $coreSources) {
            $object = Join-Path $directory ($name + '.o')
            & $toolchain.gcc @common "-$CoreMarkOptimization" @definitions -include $config -Dmain=coremark_benchmark_main -I $core -c (Join-Path $core $name) -o $object
            if ($LASTEXITCODE) { throw "CoreMark compilation failed: $name" }
            $objects += $object
        }
        foreach ($name in @('sw/bootloader/start.S','sw/bootloader/runtime.c','sim/coremark_short/main.c')) {
            $object = Join-Path $directory ([IO.Path]::GetFileName($name) + '.o')
            & $toolchain.gcc @common -O2 @definitions -Werror -c (Join-Path $root $name) -o $object
            if ($LASTEXITCODE) { throw "Integration support compilation failed: $name" }
            $objects += $object
        }
        $elf = Join-Path $directory 'coremark_short.elf'
        $bin = Join-Path $directory 'coremark_short.bin'
        & $toolchain.gcc @common @objects -nostartfiles -nostdlib "-T$linkerPath" `
            '-Wl,--gc-sections' '-Wl,--build-id=none' $toolchain.Libgcc -o $elf
        if ($LASTEXITCODE) { throw 'CoreMark integration link failed' }
        & $toolchain.objcopy -O binary $elf $bin
        if ($LASTEXITCODE) { throw 'CoreMark integration objcopy failed' }
        & (Join-Path $PSScriptRoot 'bin_to_hex.ps1') -InputBin $bin -OutputHex (Join-Path $directory 'rom.hex')
        if ($ExpectedRomSha256 -and
            (Get-FileHash -LiteralPath (Join-Path $directory 'rom.hex') -Algorithm SHA256).Hash -ne $ExpectedRomSha256) {
            throw 'Rebuilt test ROM differs from the supplied baseline; refusing a mixed-firmware CPU comparison.'
        }
        Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin -Optimization "CoreMark -$CoreMarkOptimization; support -O2; independent ITERATIONS=10 fixture" -UsesLibgcc -CoremarkDirectory $core
    }
    $model = Build-VerilatorModel -Root $root -Top 'tb_cpu_integration' -MsysRoot $MsysRoot -Sources $rtl -TimeoutSeconds 1200 -BuildJobs $BuildJobs
    # The model is a MINGW64 host executable. Reuse must select the same host
    # DLLs as Build-VerilatorModel, never the cross compiler's UCRT runtimes.
    $modelRuntimeBin = [IO.Path]::GetFullPath((Join-Path $MsysRoot 'mingw64/bin'))
    $env:PATH = $modelRuntimeBin + ';' + $env:PATH
    $modelRuntimeHashes = [ordered]@{}
    foreach ($name in @('libstdc++-6.dll','libgcc_s_seh-1.dll','libwinpthread-1.dll')) {
        $modelRuntimeHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $modelRuntimeBin $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $modelHash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()
    $results = @()
    foreach ($seedMode in $modes) {
        $directory = Join-Path $out $seedMode
        $rom = (Join-Path $directory 'rom.hex').Replace('\','/')
        $log = Join-Path $directory 'output.txt'
        $raw = Invoke-BoundedProcess -Executable $model -Arguments ('+coremark_short "+coremark_rom=' + $rom + '"') -Directory $root -Log $log -TimeoutSeconds $TimeoutSeconds
        $result = & (Join-Path $PSScriptRoot 'check_coremark_short.ps1') -Log $log -Mode $seedMode -ExpectedGccVersion $ExpectedGccVersion -CoreMarkOptimization $CoreMarkOptimization
        $results += [ordered]@{
            result = $result
            firmware = Get-Content -LiteralPath (Join-Path $directory 'coremark_short.build.json') -Raw | ConvertFrom-Json
            rom_sha256 = (Get-FileHash -LiteralPath (Join-Path $directory 'rom.hex') -Algorithm SHA256).Hash.ToLowerInvariant()
            config_sha256 = (Get-FileHash -LiteralPath (Join-Path $directory 'test_build_config.h') -Algorithm SHA256).Hash.ToLowerInvariant()
            workload_layout = $WorkloadLayout
            output_sha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        Write-Output "CPU_COREMARK_SHORT_PASS mode=$seedMode optimization=$CoreMarkOptimization ticks=$($result.measured_ticks) timer_scale=1; short result correctly rejected by production port"
    }
    foreach ($name in $inputs) {
        if ((Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$name]) { throw "Test input changed during execution: $name" }
    }
    if ((Get-FileHash -LiteralPath $linkerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $linkerHash) { throw 'Selected test linker changed during execution.' }
    if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $modelHash) { throw 'Simulation executable changed during execution.' }
    foreach ($name in $modelRuntimeHashes.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $modelRuntimeBin $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $modelRuntimeHashes[$name]) { throw "Model runtime changed: $name" }
    }
    if ($capacity) {
        $capacityAfter = Read-CompilerCapacityEvidence -Path $CapacityEvidence -Root $root -Toolchain $toolchain -Optimization $CoreMarkOptimization
        if ($capacityAfter.evidence_sha256 -ne $capacity.evidence_sha256) { throw 'Capacity evidence changed during execution.' }
    }
    $evidence = [ordered]@{
        schema_version = 1
        scope = 'Isolated official CoreMark workload + production port/CPU/wrapper/BRAM/CLINT; no board, no >=10 second score, no console command dispatch'
        command = "scripts/run_coremark_integration_test.ps1 -ExpectedGccVersion $ExpectedGccVersion -CoreMarkOptimization $CoreMarkOptimization -Mode $Mode -WorkloadLayout $WorkloadLayout -ToolchainRoot <verified toolchain>" + $(if ($capacity) { ' -CapacityEvidence <bound full-image capacity.json>' } else { '' })
        source_files = $hashes
        compiler_flags = $common + @("-$CoreMarkOptimization",'-DITERATIONS=10','-DVALIDATION_RUN=<0 or 1>','-include test_build_config.h','-Dmain=coremark_benchmark_main (all CoreMark translation units)')
        support_optimization = '-O2 (start.S, runtime.c, test main only)'
        expected_same_rom_sha256 = $ExpectedRomSha256
        capacity_binding = $capacity
        selected_linker_sha256 = $linkerHash
        host_build_jobs = $BuildJobs
        clock_interpretation = 'HDL edges are abstract CPU cycles; port seconds use candidate 49.5 MHz, not HDL wall time or board measurements.'
        model_sha256 = $modelHash
        model_runtime_sha256 = $modelRuntimeHashes
        cases = $results
    }
    [IO.File]::WriteAllText((Join-Path $out "evidence.$Mode.json"), ($evidence | ConvertTo-Json -Depth 15) + "`n", [Text.UTF8Encoding]::new($false))
    Write-Output "CPU_COREMARK_INTEGRATION_PASS evidence=$out\evidence.$Mode.json"
} finally {
    $env:PATH = $originalPath
}
