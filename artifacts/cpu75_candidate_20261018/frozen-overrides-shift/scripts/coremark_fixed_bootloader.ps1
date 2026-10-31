param(
    [ValidateRange(1,1000000)][int]$Iterations = 10,
    [ValidateSet('Pilot','Candidate')][string]$Purpose = 'Pilot',
    [ValidateRange(1,1000000000)][int]$CpuHz = 75000000,
    [string]$ToolchainRoot = '',
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$out = [IO.Path]::GetFullPath($OutputDirectory)
$production = Join-Path $root 'artifacts/bootloader.bin'
if (!(Test-Path -LiteralPath $production -PathType Leaf)) { throw 'Missing current production bootloader.' }
$socHeader = [IO.File]::ReadAllText((Join-Path $root 'sw/bootloader/soc.h'))
$coremarkHeader = [IO.File]::ReadAllText((Join-Path $root 'sw/coremark/core_portme.h'))
if ($socHeader -cnotmatch ('(?m)^#define CPU_CLOCK_HZ ' + $CpuHz + 'u$') -or
    $coremarkHeader -cnotmatch '(?m)^#define CORE_CLOCKS_PER_SEC 49500000ULL$') {
    throw 'Fixed-iteration firmware clock differs from the source bootloader/CoreMark constants.'
}
if ($out.TrimEnd('\','/').Equals((Join-Path $root 'artifacts'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Fixed-iteration build must not replace production artifacts directly.'
}
$originalPath = $env:PATH
try {
    $toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
    $boot = Join-Path $root 'sw/bootloader'
    $core = Join-Path $root 'sw/coremark'
    Assert-CpuCoremarkSources -Directory $core
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $objDir = Join-Path $out 'obj'
    New-Item -ItemType Directory -Force -Path $objDir | Out-Null
    $common = @('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany',
        '-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin',
        '-fno-common','-ffunction-sections','-fdata-sections','-Wall','-Wextra')
    $objects = New-Object 'Collections.Generic.List[string]'
    $inputs = [ordered]@{}
    $bootSources = @('start.S','runtime.c','console_line.c','flash.c','net.c','camera.c',
        'camera_sd.c','crc32_fast.c','png_rgb565.c','fat_camera.c','fat_ro.c','sd_native.c',
        'sd_boot.c','audio_sample.c','audio.c','main.c')
    foreach ($name in $bootSources) {
        $source = Join-Path $boot $name
        $object = Join-Path $objDir (([IO.Path]::GetFileNameWithoutExtension($name))+'.o')
        $optimization = if ($name -in @('camera.c','crc32_fast.c','png_rgb565.c')) { '-O2' } else { '-Os' }
        & $toolchain.gcc @common $optimization -flto -Werror -I $boot -c $source -o $object
        if ($LASTEXITCODE) { throw "Fixed bootloader compile failed: $name" }
        $objects.Add($object)
        $inputs["sw/bootloader/$name"] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $coreSources = @('core_main.c','core_list_join.c','core_matrix.c','core_state.c',
        'core_util.c','core_portme.c')
    foreach ($name in $coreSources) {
        $source = Join-Path $core $name
        $object = Join-Path $objDir (([IO.Path]::GetFileNameWithoutExtension($name))+'.o')
        & $toolchain.gcc @common -O2 -I $core -Dmain=coremark_benchmark_main `
            "-DITERATIONS=$Iterations" -c $source -o $object
        if ($LASTEXITCODE) { throw "Fixed CoreMark compile failed: $name" }
        $objects.Add($object)
        $inputs["sw/coremark/$name"] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    foreach ($name in @('sw/bootloader/link.ld','sw/bootloader/soc.h','sw/coremark/core_portme.h',
                       'sw/coremark/coremark.h','sw/coremark/upstream.json')) {
        $inputs[$name] = (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $elf = Join-Path $out 'fixed_bootloader.elf'
    $bin = Join-Path $out 'fixed_bootloader.bin'
    $rom = Join-Path $out 'fixed_bootrom.hex'
    $linker = Join-Path $boot 'link.ld'
    & $toolchain.gcc @common @($objects.ToArray()) -flto -nostartfiles -nostdlib "-T$linker" `
        '-Wl,--gc-sections' '-Wl,--build-id=none' $toolchain.Libgcc -o $elf
    if ($LASTEXITCODE) { throw 'Fixed bootloader link failed.' }
    & $toolchain.objcopy -O binary $elf $bin
    if ($LASTEXITCODE) { throw 'Fixed bootloader objcopy failed.' }
    & (Join-Path $PSScriptRoot 'bin_to_hex.ps1') -InputBin $bin -OutputHex $rom -MemoryBytes 131072
    Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
        -Optimization "CoreMark -O2 -DITERATIONS=$Iterations; other bootloader code keeps production optimization" `
        -UsesLibgcc -CoremarkDirectory $core
    $buildPath = [IO.Path]::ChangeExtension($bin,'.build.json')
    $buildRecord = Get-Content -LiteralPath $buildPath -Raw -Encoding utf8 | ConvertFrom-Json
    $buildRecord | Add-Member -NotePropertyName coremark_iterations -NotePropertyValue $Iterations
    [IO.File]::WriteAllText($buildPath, ($buildRecord | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
    $evidence = [ordered]@{
        status = if ($Purpose -eq 'Pilot') { 'PILOT_ONLY_NOT_RELEASE_FIRMWARE' } else { 'FIXED_ITERATION_CANDIDATE_NOT_PROMOTED' }
        purpose = $Purpose
        iterations = $Iterations
        cpu_hz = $CpuHz
        isa = $CpuMarch
        abi = $CpuAbi
        production_bootloader_sha256 = (Get-FileHash -LiteralPath $production -Algorithm SHA256).Hash.ToLowerInvariant()
        fixed_bin_sha256 = (Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLowerInvariant()
        fixed_rom_sha256 = (Get-FileHash -LiteralPath $rom -Algorithm SHA256).Hash.ToLowerInvariant()
        cpu_rtl_sha256 = (Get-FileHash -LiteralPath (Join-Path $root 'rtl/cpu/CoreTop.sv') -Algorithm SHA256).Hash.ToLowerInvariant()
        source_files = $inputs
        scope = 'Complete production-source bootloader and GCC/ISA recipe with explicit fixed CoreMark iterations. Candidate must be promoted and FPGA rebuilt before release.'
    }
    [IO.File]::WriteAllText((Join-Path $out 'fixed-build.json'), ($evidence | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
    Write-Output "FIXED_BOOTLOADER_BUILD_PASS purpose=$Purpose iterations=$Iterations rom=$rom"
} finally {
    $env:PATH = $originalPath
}
