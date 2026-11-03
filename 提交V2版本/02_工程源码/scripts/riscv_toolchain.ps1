# Competition-aligned native toolchain. Verify the actual configured target;
# do not substitute a renamed riscv64/riscv-none executable.
$CpuMarch = 'rv32ima_zicsr_zifencei'
$CpuAbi = 'ilp32'
function Resolve-CpuCoremarkOptimization([object]$Profile) {
    $names = @()
    if ($null -ne $Profile) { $names = @($Profile.PSObject.Properties | ForEach-Object { $_.Name }) }
    $recipe = 'baseline'
    if ('coremark_compiler_profile' -cin $names) {
        if ($Profile.coremark_compiler_profile -isnot [string]) { throw 'CoreMark compiler profile must be a string.' }
        $recipe = $Profile.coremark_compiler_profile
    }
    $zbc = $false
    if ('zbc_candidate' -cin $names) {
        if ($Profile.zbc_candidate -isnot [bool]) { throw 'CPU Zbc selection must be a JSON boolean.' }
        $zbc = $Profile.zbc_candidate
    }
    $optimization = @('-O2')
    if ($zbc) { $optimization += @('-fno-if-conversion','-fno-if-conversion2') }
    switch -CaseSensitive ($recipe) {
        'baseline' { }
        'cm60-unroll2-lto-branch1' {
            if (!$zbc) { throw 'CM6.0 compiler profile requires the paired Zbc CPU.' }
            $optimization += @('-funroll-loops','--param=max-unroll-times=2','-flto','-mbranch-cost=1')
        }
        default { throw "Unknown CoreMark compiler profile: $recipe" }
    }
    return $optimization
}
$cpuProfileRoot = Split-Path -Parent $PSScriptRoot
$cpuProfileManifest = Join-Path $cpuProfileRoot 'rtl/cpu/source.json'
$cpuProfile = $null
if (Test-Path -LiteralPath $cpuProfileManifest) {
    $cpuProfile = Get-Content -LiteralPath $cpuProfileManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if (($cpuProfile.PSObject.Properties.Name -contains 'zbc_candidate') -and $cpuProfile.zbc_candidate -isnot [bool]) {
        throw 'CPU Zbc selection must be a JSON boolean.'
    }
    if ($cpuProfile.zbc_candidate -eq $true) {
        $cpuEmit = Get-Content -LiteralPath (Join-Path $cpuProfileRoot 'rtl/cpu/emit-config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cpuProfile.isa -cne 'rv32ima_zicsr_zifencei_zbc' -or
            $cpuProfile.software_march -cne $cpuProfile.isa -or $cpuEmit.zbc -isnot [bool] -or $cpuEmit.zbc -ne $true -or
            $cpuEmit.isa -cne $cpuProfile.isa -or
            (Get-FileHash -LiteralPath (Join-Path $cpuProfileRoot 'rtl/cpu/emit-config.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $cpuProfile.config_sha256 -or
            (Get-FileHash -LiteralPath (Join-Path $cpuProfileRoot 'rtl/cpu/CoreTop.sv') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $cpuProfile.sha256) {
            throw 'Zbc compiler selection requires matching CPU RTL, emit configuration and source manifest.'
        }
        $CpuMarch = $cpuProfile.isa
    }
}
$CpuCoremarkOptimization = @(Resolve-CpuCoremarkOptimization $cpuProfile)
$CpuGccVersion = '16.2.0'
$CpuTarget = 'riscv32-unknown-elf'

function Build-CpuObjects {
    param($Toolchain, [string]$Directory, [string[]]$Sources,
          [string[]]$CompilerArguments)
    # GCC's direct multi-source link gives assembly inputs random cc*.o FILE
    # symbols. Stable object basenames preserve ELF and manifest reproducibility.
    New-Item -ItemType Directory -Force -Path $Directory | Out-Null
    $objects = New-Object 'Collections.Generic.List[string]'
    for ($index = 0; $index -lt $Sources.Count; $index++) {
        $name = '{0:D2}_{1}.o' -f $index, [IO.Path]::GetFileName($Sources[$index])
        $object = Join-Path $Directory $name
        & $Toolchain.gcc @CompilerArguments -c $Sources[$index] -o $object
        if ($LASTEXITCODE) { throw "Compilation failed: $($Sources[$index]) ($LASTEXITCODE)" }
        $objects.Add($object)
    }
    return $objects.ToArray()
}

function Assert-CpuCoremarkSources {
    param([string]$Directory)
    $provenance = Get-Content -LiteralPath (Join-Path $Directory 'upstream.json') -Raw | ConvertFrom-Json
    if ($provenance.commit -ne 'cfa9ab377835911f23d9b0831c7be302ed1f58de') {
        throw 'CoreMark source must use the reviewed fixed official upstream revision.'
    }
    $files = @('core_list_join.c','core_main.c','core_matrix.c','core_state.c','core_util.c','coremark.h')
    if (@($provenance.files.PSObject.Properties).Count -ne $files.Count) { throw 'Incomplete CoreMark source manifest.' }
    foreach ($name in $files) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $Directory $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $provenance.files.$name) { throw "Modified official CoreMark file: $name" }
    }
}

function Assert-CpuElf {
    param([string]$Readelf, [string]$Path)
    $metadata = (& $Readelf -h -A $Path | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect ELF metadata: $Path" }
    $classes = [regex]::Matches($metadata, '(?m)^\s*Class:\s*(\S+)')
    $machines = [regex]::Matches($metadata, '(?m)^\s*Machine:\s*(.+)$')
    $flags = [regex]::Matches($metadata, '(?m)^\s*Flags:\s*(0x[0-9a-fA-F]+)')
    if (!$classes.Count -or $classes.Count -ne $machines.Count -or $classes.Count -ne $flags.Count) {
        throw "Incomplete ELF member headers: $Path"
    }
    foreach ($entry in $classes) {
        if ($entry.Groups[1].Value -ne 'ELF32') { throw "Non-ELF32 member: $Path" }
    }
    foreach ($entry in $machines) {
        if ($entry.Groups[1].Value.Trim() -ne 'RISC-V') { throw "Non-RISC-V member: $Path" }
    }
    foreach ($entry in $flags) {
        if ([Convert]::ToUInt32($entry.Groups[1].Value.Substring(2), 16) -ne 0) {
            throw "ELF member requires RVC, non-soft-float ABI, or unsupported flags: $Path"
        }
    }
    $architectures = [regex]::Matches($metadata, 'Tag_RISCV_arch:\s*"([^"]+)"')
    if (!$architectures.Count) { throw "Missing ISA attributes: $Path" }
    foreach ($entry in $architectures) {
        $architecture = $entry.Groups[1].Value
        if ($architecture -notmatch '^rv32i[0-9]') { throw "Unsupported ISA $architecture in $Path" }
        foreach ($extension in ($architecture.Substring(4) -split '_')) {
            $name = [regex]::Match($extension, '^[a-z]+').Value
            # New binutils spells out the M/A subsets in ELF attributes.
            $allowedExtensions = @('i', 'm', 'a', 'zicsr', 'zifencei', 'zmmul', 'zaamo', 'zalrsc')
            if ($CpuMarch -eq 'rv32ima_zicsr_zifencei_zbc') { $allowedExtensions += 'zbc' }
            if ($name -notin $allowedExtensions) {
                throw "Unsupported ISA extension $extension in $Path"
            }
        }
    }
    return [pscustomobject]@{
        ElfMembers = $classes.Count
        ElfClass = 'ELF32'
        Flags = '0x0 (soft-float ABI, no RVC)'
        Architectures = @($architectures | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    }
}

function Get-CpuToolchain {
    param([string]$ToolchainRoot = '', [string]$ToolchainBin = '')
    if ($ToolchainRoot -and $ToolchainBin) { throw 'Pass ToolchainRoot or ToolchainBin, not both.' }
    if (!$ToolchainBin) {
        if ($ToolchainRoot) { $ToolchainBin = Join-Path $ToolchainRoot 'bin' }
        elseif ($env:CPU_TOOLCHAIN) { $ToolchainBin = Join-Path $env:CPU_TOOLCHAIN 'bin' }
        else {
            $onPath = Get-Command 'riscv32-unknown-elf-gcc.exe' -ErrorAction SilentlyContinue
            if ($onPath) { $ToolchainBin = Split-Path -Parent $onPath.Source }
            else { throw "GCC $CpuGccVersion riscv32-unknown-elf is required; pass -ToolchainRoot/-ToolchainBin, set CPU_TOOLCHAIN, or add its bin directory to PATH." }
        }
    }
    $ToolchainBin = [IO.Path]::GetFullPath($ToolchainBin)
    $tools = [ordered]@{ Bin = $ToolchainBin; Root = (Split-Path -Parent $ToolchainBin) }
    foreach ($name in @('gcc', 'objcopy', 'objdump', 'size', 'readelf', 'nm')) {
        $path = Join-Path $ToolchainBin "riscv32-unknown-elf-$name.exe"
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing $path. Pass a GCC $CpuGccVersion riscv32-unknown-elf ToolchainRoot/Bin or set CPU_TOOLCHAIN."
        }
        $tools[$name] = $path
    }
    # GCC and cc1 need the package's adjacent native runtime DLLs. Every
    # build/test entry point saves PATH before this call and restores it in
    # finally, covering both tool validation and later compiler failures.
    if (($env:PATH -split ';')[0] -ne $ToolchainBin) { $env:PATH = $ToolchainBin + ';' + $env:PATH }
    $target = (& $tools.gcc -dumpmachine | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $target -ne $CpuTarget) { throw "Wrong compiler target: $target" }
    $version = (& $tools.gcc -dumpfullversion | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $version -ne $CpuGccVersion) { throw "Expected GCC $CpuGccVersion, got $version" }
    $tools['Target'] = $target
    $tools['Version'] = $version
    # This official release can fall back to its double-float default for
    # IMA. Reject it by metadata, then query the compatible IM soft-float
    # multilib. Firmware itself always keeps the complete IMA march above.
    $selected = $false
    $reasons = @()
    foreach ($libraryMarch in @('rv32ima', 'rv32im')) {
        $library = (& $tools.gcc "-march=$libraryMarch" -mabi=ilp32 -print-libgcc-file-name | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $library -PathType Leaf)) {
            $reasons += "${libraryMarch}: missing library"
            continue
        }
        try { $metadata = Assert-CpuElf -Readelf $tools.readelf -Path $library }
        catch { $reasons += "${libraryMarch}: $($_.Exception.Message)"; continue }
        $tools['Libgcc'] = [IO.Path]::GetFullPath($library)
        $tools['LibgccMetadata'] = $metadata
        $tools['LibgccMarch'] = $libraryMarch
        $tools['LibgccSha256'] = (Get-FileHash -LiteralPath $library -Algorithm SHA256).Hash.ToLowerInvariant()
        $selected = $true
        break
    }
    if (!$selected) { throw ('No compatible RV32/ILP32 libgcc: ' + ($reasons -join '; ')) }
    return [pscustomobject]$tools
}

function Assert-CpuCode {
    param($Toolchain, [string]$Elf, [switch]$IllegalInstructionFixture)
    $symbols = (& $Toolchain.nm -n $Elf | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect code bounds: $Elf" }
    $start = [regex]::Match($symbols, '(?m)^([0-9a-fA-F]+)\s+\S\s+__cpu_code_start\s*$')
    $end = [regex]::Match($symbols, '(?m)^([0-9a-fA-F]+)\s+\S\s+__cpu_code_end\s*$')
    if (!$start.Success -or !$end.Success) { throw "Missing explicit code/data boundaries: $Elf" }
    $codeStart = [Convert]::ToUInt32($start.Groups[1].Value, 16)
    $codeEnd = [Convert]::ToUInt32($end.Groups[1].Value, 16)
    if ($codeEnd -le $codeStart -or ($codeStart -band 3) -or ($codeEnd -band 3)) {
        throw "Invalid IALIGN=32 code bounds: $Elf"
    }
    $fixtureStart = [uint32]0
    if ($IllegalInstructionFixture) {
        $first = [regex]::Match($symbols, '(?m)^([0-9a-fA-F]+)\s+\S\s+__cpu_illegal_start\s*$')
        $last = [regex]::Match($symbols, '(?m)^([0-9a-fA-F]+)\s+\S\s+__cpu_illegal_end\s*$')
        if (!$first.Success -or !$last.Success) { throw 'Missing explicit illegal-instruction test fixture bounds.' }
        $fixtureStart = [Convert]::ToUInt32($first.Groups[1].Value, 16)
        if ([Convert]::ToUInt32($last.Groups[1].Value, 16) -ne $fixtureStart + 4) {
            throw 'Illegal-instruction test fixture must occupy exactly four bytes.'
        }
    }
    $disassembly = (& $Toolchain.objdump -d -M no-aliases "--start-address=$codeStart" "--stop-address=$codeEnd" $Elf | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Cannot disassemble linked instructions: $Elf" }
    $allowed = @('lui','auipc','jal','jalr','beq','bne','blt','bge','bltu','bgeu',
        'lb','lh','lw','lbu','lhu','sb','sh','sw','addi','slti','sltiu','xori','ori','andi',
        'slli','srli','srai','add','sub','sll','slt','sltu','xor','srl','sra','or','and',
        'fence','fence.i','ecall','ebreak','mret','wfi',
        'csrrw','csrrs','csrrc','csrrwi','csrrsi','csrrci',
        'mul','mulh','mulhsu','mulhu','div','divu','rem','remu',
        'lr.w','sc.w','amoadd.w','amoswap.w','amoxor.w','amoor.w','amoand.w',
        'amomin.w','amomax.w','amominu.w','amomaxu.w')
    $bytesChecked = 0
    if ($CpuMarch -eq 'rv32ima_zicsr_zifencei_zbc') { $allowed += @('clmul','clmulh','clmulr') }
    foreach ($line in ($disassembly -split "`n")) {
        $instruction = [regex]::Match($line, '^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)')
        if (!$instruction.Success) { continue }
        $address = [Convert]::ToUInt32($instruction.Groups[1].Value, 16)
        $encoding = $instruction.Groups[2].Value
        if ($IllegalInstructionFixture -and $address -ge $fixtureStart -and $address -lt $fixtureStart + 4) {
            if ($encoding -eq '00010001' -and $address -eq $fixtureStart) { $bytesChecked += 4 }
            elseif ($encoding -eq '0001') { $bytesChecked += 2 }
            else { throw "Unexpected illegal-test bytes: $line" }
            continue
        }
        $mnemonic = $instruction.Groups[3].Value -replace '\.(aqrl|aq|rl)$', ''
        if ($encoding.Length -ne 8 -or ($address -band 3) -or $mnemonic -notin $allowed) {
            throw "Linked code violates RV32IMA instruction contract: $line"
        }
        $word = [Convert]::ToUInt32($encoding, 16)
        if (($word -band 127) -eq 115 -and (($word -shr 12) -band 7) -ne 0 -and ($word -shr 20) -eq 0xc22) {
            throw "Linked code accesses unsupported vector vlenb CSR: $line"
        }
        $bytesChecked += 4
    }
    if ($bytesChecked -ne $codeEnd - $codeStart) { throw "Disassembly did not cover the complete code region: $Elf" }
    return [pscustomobject]@{
        CodeStart = ('0x{0:x8}' -f $codeStart)
        CodeEndExclusive = ('0x{0:x8}' -f $codeEnd)
        BytesChecked = $bytesChecked
        Result = "$CpuMarch mnemonic/width whitelist; no vlenb; rodata excluded by linker symbols"
        ExplicitIllegalInstructionFixture = [bool]$IllegalInstructionFixture
    }
}

function Write-CpuFirmwareEvidence {
    param($Toolchain, [string]$Elf, [string]$Binary,
          [string]$Optimization, [switch]$UsesLibgcc, [switch]$IllegalInstructionFixture,
          [string]$CoremarkDirectory = '', $BuildCommands = $null, $BuildInputs = $null,
          $StackLayout = $null, $CoremarkContract = $null,
          [Nullable[int]]$CoremarkIterations = $null)
    $elfMetadata = Assert-CpuElf -Readelf $Toolchain.readelf -Path $Elf
    $codeMetadata = Assert-CpuCode -Toolchain $Toolchain -Elf $Elf -IllegalInstructionFixture:$IllegalInstructionFixture
    $record = [ordered]@{
        compiler = 'riscv32-unknown-elf-gcc'
        compiler_target = $Toolchain.Target
        compiler_version = $Toolchain.Version
        compiler_sha256 = (Get-FileHash -LiteralPath $Toolchain.gcc -Algorithm SHA256).Hash.ToLowerInvariant()
        march = $CpuMarch
        abi = $CpuAbi
        optimization = $Optimization
        elf = [IO.Path]::GetFileName($Elf)
        elf_sha256 = (Get-FileHash -LiteralPath $Elf -Algorithm SHA256).Hash.ToLowerInvariant()
        elf_metadata = $elfMetadata
        code_validation = $codeMetadata
        binary = [IO.Path]::GetFileName($Binary)
        binary_sha256 = (Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash.ToLowerInvariant()
        libgcc = $null
    }
    if ($CoremarkDirectory) {
        Assert-CpuCoremarkSources -Directory $CoremarkDirectory
        $record['coremark_source'] = Get-Content -LiteralPath (Join-Path $CoremarkDirectory 'upstream.json') -Raw | ConvertFrom-Json
        $record['coremark_seed_modes'] = 'runtime performance 0/0/0x66; validation 0x3415/0x3415/0x66; 2000 bytes'
    }
    if ($null -ne $BuildCommands) { $record['build_commands'] = $BuildCommands }
    if ($null -ne $BuildInputs) { $record['build_inputs'] = $BuildInputs }
    if ($null -ne $StackLayout) { $record['stack_layout'] = $StackLayout }
    if ($null -ne $CoremarkContract) { $record['coremark_contract'] = $CoremarkContract }
    if ($null -ne $CoremarkIterations) { $record['coremark_iterations'] = [int]$CoremarkIterations }
    if ($UsesLibgcc) {
        $rootPrefix = $Toolchain.Root.TrimEnd('\', '/') + '\'
        if (!$Toolchain.Libgcc.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Selected libgcc is outside the verified toolchain root.'
        }
        $record.libgcc = [ordered]@{
            selected_by = "gcc -march=$($Toolchain.LibgccMarch) -mabi=ilp32 -print-libgcc-file-name"
            toolchain_relative_path = $Toolchain.Libgcc.Substring($rootPrefix.Length).Replace('\', '/')
            sha256 = $Toolchain.LibgccSha256
            metadata = $Toolchain.LibgccMetadata
        }
    }
    $report = [IO.Path]::ChangeExtension($Binary, '.build.json')
    [IO.File]::WriteAllText($report, ($record | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
    # Keep the production artifact manifest current after every native build.
    # Simulation firmware has its own temporary output directory.
    $directory = Split-Path -Parent ([IO.Path]::GetFullPath($Binary))
    if ((Split-Path -Leaf $directory) -eq 'artifacts' -and (Split-Path -Leaf $Binary) -ne 'hello.bin') {
        $hashPath = Join-Path $directory 'SHA256SUMS.txt'
        $names = @([IO.Path]::GetFileName($Elf), [IO.Path]::GetFileName($Binary),
            [IO.Path]::GetFileName($report))
        [string[]]$lines = @()
        if (Test-Path -LiteralPath $hashPath) {
            $lines = @([IO.File]::ReadAllLines($hashPath) | Where-Object {
                $_ -match '^[0-9a-f]{64}  [A-Za-z0-9_.-]+$' -and
                ($_ -split '\s+', 2)[1] -notin $names
            })
        }
        foreach ($path in @($Elf, $Binary, $report)) {
            $lines += (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() +
                '  ' + [IO.Path]::GetFileName($path)
        }
        [IO.File]::WriteAllText($hashPath, ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    }
}
