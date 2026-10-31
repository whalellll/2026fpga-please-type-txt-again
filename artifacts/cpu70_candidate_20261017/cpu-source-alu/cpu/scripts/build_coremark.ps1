param(
    [ValidateRange(1, 2147483647)][int]$Iterations = 10,
    [ValidateRange(1, 1000000000)][long]$CpuHz = 49500000,
    [string]$ToolchainRoot = $env:RISCV_TOOLCHAIN_ROOT,
    [string]$OutputRoot = '',
    [ValidateSet('14.2.0', '16.2.0')][string]$CompilerVersion = '16.2.0',
    [ValidateSet('O2', 'O3')][string]$Optimization = 'O2',
    [ValidateSet('performance', 'validation')][string]$RunMode = 'performance',
    [ValidateSet('calibration', 'formal_candidate')][string]$EvidenceClass = 'calibration'
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (!$OutputRoot) { $OutputRoot = Join-Path $projectRoot 'coremark_test_soc/sim/coremark_ima' }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (!$ToolchainRoot) {
    $gccCommand = Get-Command 'riscv32-unknown-elf-gcc.exe' -ErrorAction SilentlyContinue
    if (!$gccCommand) { throw 'Specify -ToolchainRoot or RISCV_TOOLCHAIN_ROOT for the selected riscv32-unknown-elf GCC version.' }
    $ToolchainRoot = Split-Path (Split-Path $gccCommand.Source -Parent) -Parent
}
$toolBin = Join-Path $ToolchainRoot 'bin'
$gcc = Join-Path $toolBin 'riscv32-unknown-elf-gcc.exe'
$objcopy = Join-Path $toolBin 'riscv32-unknown-elf-objcopy.exe'
$objdump = Join-Path $toolBin 'riscv32-unknown-elf-objdump.exe'
$readelf = Join-Path $toolBin 'riscv32-unknown-elf-readelf.exe'
$sizeTool = Join-Path $toolBin 'riscv32-unknown-elf-size.exe'
foreach ($tool in @($gcc, $objcopy, $objdump, $readelf, $sizeTool)) {
    if (!(Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Missing tool: $tool" }
}
$version = (& $gcc -dumpfullversion | Out-String).Trim()
$target = (& $gcc -dumpmachine | Out-String).Trim()
if ($version -ne $CompilerVersion -or $target -ne 'riscv32-unknown-elf') {
    throw "Expected genuine riscv32-unknown-elf GCC $CompilerVersion; got $target / $version."
}
# The GCC 14.2 comparison package needs its RV32IM multilib selected explicitly.
# The selected GCC 16.2 toolchain has one default RV32IMA/ILP32 library.
# Application compilation remains RV32IMA/Zicsr/Zifencei in both cases.
$libraryMarch = if ($version -eq '14.2.0') { 'rv32im' } else { 'rv32ima' }
$libgcc = (& $gcc "-march=$libraryMarch" '-mabi=ilp32' '-print-libgcc-file-name' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $libgcc -PathType Leaf)) {
    throw 'Missing the compiler-selected RV32IMA/ILP32-compatible libgcc.'
}
$multilib = (& $gcc "-march=$libraryMarch" '-mabi=ilp32' '-print-multi-directory' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the selected libgcc multilib.' }
$libraryInfo = (& $readelf -h -A $libgcc | Out-String)
if ($LASTEXITCODE -ne 0 -or $libraryInfo -notmatch 'Class:\s+ELF32' -or
    $libraryInfo -match 'Class:\s+ELF64|Flags:.*(?:RVC|single-float|double-float)|Tag_RISCV_arch:.*_(?:c|f|d|v)[0-9]') {
    throw 'libgcc must contain only RV32 soft-float code without compressed instructions.'
}
$toolchainFullPath = [IO.Path]::GetFullPath($ToolchainRoot).TrimEnd('\','/')
$libgccFullPath = [IO.Path]::GetFullPath($libgcc)
if (!$libgccFullPath.StartsWith($toolchainFullPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Selected libgcc is outside the configured toolchain.'
}
$portableLibgcc = '<toolchain>/' + $libgccFullPath.Substring($toolchainFullPath.Length + 1).Replace('\','/')
$utf8 = [Text.UTF8Encoding]::new($false)
$sources = @('coremark_test_soc/sw/start.S') + @(
    'core_main.c', 'core_list_join.c', 'core_matrix.c', 'core_state.c',
    'core_util.c', 'core_portme.c'
) | ForEach-Object {
    if ($_ -like '*.S') { $_ } else { "coremark_test_soc/sw/coremark/$_" }
}
$linker = 'coremark_test_soc/sw/link.ld'
$upstreamFile = 'coremark_test_soc/sw/coremark/upstream.json'
$upstream = Get-Content -LiteralPath (Join-Path $projectRoot $upstreamFile) -Raw -Encoding UTF8 | ConvertFrom-Json
if ($upstream.commit -ne 'cfa9ab377835911f23d9b0831c7be302ed1f58de' -or @($upstream.files.PSObject.Properties).Count -ne 6) {
    throw 'Expected the fixed official CoreMark 1.0 source set.'
}
foreach ($entry in $upstream.files.PSObject.Properties) {
    $officialFile = Join-Path $projectRoot ("coremark_test_soc/sw/coremark/" + $entry.Name)
    if ((Get-FileHash -LiteralPath $officialFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Official CoreMark source was modified: $($entry.Name)"
    }
}
$sourceFiles = @($sources) + @($linker) + @(
    'coremark_test_soc/sw/coremark/coremark.h',
    'coremark_test_soc/sw/coremark/core_portme.h',
    'scripts/build_coremark.ps1', $upstreamFile
)
$sourceHashes = [ordered]@{}
foreach ($sourceFile in $sourceFiles) {
    $sourceHashes[$sourceFile] = (Get-FileHash -LiteralPath (Join-Path $projectRoot $sourceFile) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$variants = @('rv32ima')
Write-Output 'CoreMark firmware build: normally under 30 seconds; Ctrl+C stops the compiler.'
$savedPath = $env:PATH
Push-Location -LiteralPath $projectRoot
try {
    # cc1 lives below lib/gcc and resolves its UCRT runtime DLLs via PATH.
    $env:PATH = $toolBin + ';' + $savedPath
    foreach ($variant in $variants) {
        $march = "${variant}_zicsr_zifencei"
        $outDir = $OutputRoot
        $objectDir = Join-Path $projectRoot "work/coremark-build/$variant/$CompilerVersion/$Optimization/$RunMode"
        New-Item -ItemType Directory -Path $outDir, $objectDir -Force | Out-Null
        $elf = Join-Path $outDir 'coremark.elf'
        $bin = Join-Path $outDir 'coremark.bin'
        $config = Join-Path $outDir 'coremark_build_config.h'
        $reportedFlags = "-$Optimization -march=$march -mabi=ilp32 -mcmodel=medany -mno-relax -msmall-data-limit=0 -mstrict-align -ffreestanding -fno-builtin -fno-common -ffunction-sections -fdata-sections"
        $configText = @(
            "#define ITERATIONS $Iterations",
            "#define PERFORMANCE_RUN $([int]($RunMode -eq 'performance'))",
            "#define VALIDATION_RUN $([int]($RunMode -eq 'validation'))",
            "#define PROFILE_RUN 0",
            "#define CORE_CLOCKS_PER_SEC ${CpuHz}ULL",
            "#define COMPILER_VERSION `"GCC $version ($target)`"",
            "#define COMPILER_FLAGS `"$reportedFlags`""
        ) -join "`n"
        [IO.File]::WriteAllText($config, $configText + "`n", $utf8)
        $compileFlags = @(
            '-std=gnu99', "-$Optimization", "-march=$march", '-mabi=ilp32', '-mcmodel=medany',
            '-mno-relax', '-msmall-data-limit=0', '-mstrict-align',
            '-ffreestanding', '-fno-builtin', '-fno-common',
            '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra',
            '-Icoremark_test_soc/sw/coremark', '-include', $config
        )
        # Explicit object names avoid GCC's random ccXXXX.o FILE symbol from
        # assembling start.S during a single compile-and-link invocation.
        $objects = @()
        $compileCommands = @()
        $diagnostics = ''
        foreach ($sourceFile in $sources) {
            $objectFile = Join-Path $objectDir ([IO.Path]::GetFileNameWithoutExtension($sourceFile) + '.o')
            $compileArguments = $compileFlags + @('-c', $sourceFile, '-o', $objectFile)
            $previousPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            $diagnostics += (& $gcc @compileArguments 2>&1 | Out-String)
            $compileExit = $LASTEXITCODE
            $ErrorActionPreference = $previousPreference
            if ($compileExit -ne 0) { throw "CoreMark $variant compilation failed: $diagnostics" }
            $objects += $objectFile
            $compileCommands += ,@($compileArguments | ForEach-Object {
                $_.Replace($outDir, '<output>').Replace($objectDir, '<objects>')
            })
        }
        $arguments = $compileFlags + $objects + @(
            '-nostartfiles', '-nostdlib', '-T', $linker, '-Wl,--gc-sections',
            '-Wl,--build-id=none', "-Wl,-Map,$objectDir/coremark.map", $libgcc, '-o', $elf
        )
        # Capture native warnings without PowerShell 5.1 turning them into
        # terminating NativeCommandError records. The compiler exit code wins.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $diagnostics += (& $gcc @arguments 2>&1 | Out-String)
        $compileExit = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
        [IO.File]::WriteAllText((Join-Path $objectDir 'build-diagnostics.txt'), $diagnostics, $utf8)
        if ($compileExit -ne 0) { throw "CoreMark $variant compilation failed: $diagnostics" }
        & $objcopy -O binary $elf $bin
        if ($LASTEXITCODE -ne 0) { throw 'objcopy failed' }
        $elfInfo = (& $readelf -h -A $elf | Out-String)
        if ($LASTEXITCODE -ne 0 -or $elfInfo -notmatch 'Class:\s+ELF32' -or
            $elfInfo -notmatch 'Tag_RISCV_arch:.*_m.*_a.*_zicsr.*_zifencei') {
            throw 'ELF must be RV32IMA with Zicsr/Zifencei and ILP32.'
        }
        $hasCompressed = $elfInfo -match 'Tag_RISCV_arch:.*_c[0-9]'
        if ($hasCompressed -or $elfInfo -notmatch 'Flags:\s+0x0\b') { throw 'IMA firmware must use ELF32 soft-float without RVC' }
        [IO.File]::WriteAllText((Join-Path $objectDir 'elf-info.txt'), $elfInfo, $utf8)
        $disassembly = (& $objdump -d -M no-aliases $elf | Out-String)
        if ($LASTEXITCODE -ne 0) { throw 'objdump failed' }
        [IO.File]::WriteAllText((Join-Path $objectDir 'coremark.disasm.txt'), $disassembly, $utf8)
        $shortCount = [regex]::Matches($disassembly, '(?m)^\s*[0-9a-f]+:\s+[0-9a-f]{4}\s').Count
        $wordCount = [regex]::Matches($disassembly, '(?m)^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s').Count
        if ($shortCount -ne 0) { throw 'IMA firmware contains compressed instructions' }
        # Executable sections contain code only (rodata has its own section).
        # Check the linked image too: optional library members can contain
        # instructions/CSRs that are absent from their ELF ISA attributes.
        if ($wordCount -eq 0 -or $disassembly -match '\.insn\b|\bvlenb\b|\b0xc22\b') {
            throw 'Linked firmware contains unsupported or undecodable instructions'
        }
        $sizes = (& $sizeTool -B $elf | Out-String)
        $sizeMatch = [regex]::Match($sizes, '(?m)^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[0-9a-f]+\s+')
        if ($LASTEXITCODE -ne 0 -or !$sizeMatch.Success) { throw 'Cannot parse ELF section sizes' }
        [IO.File]::WriteAllText((Join-Path $objectDir 'size.txt'), $sizes, $utf8)
        $macros = (& $gcc @compileFlags -dM -E 'coremark_test_soc/sw/coremark/core_main.c' | Out-String)
        if ($LASTEXITCODE -ne 0 -or $macros -match '(?m)^#define COREMARK_SIM\b') { throw 'Invalid CoreMark preprocessing' }
        $expectedPerformance = [int]($RunMode -eq 'performance')
        $expectedValidation = [int]($RunMode -eq 'validation')
        foreach ($definition in @("PERFORMANCE_RUN $expectedPerformance", "VALIDATION_RUN $expectedValidation",
            'PROFILE_RUN 0', "ITERATIONS $Iterations", "CORE_CLOCKS_PER_SEC ${CpuHz}ULL",
            'TOTAL_DATA_SIZE 2*1000')) {
            if ($macros -notmatch ('(?m)^#define ' + [regex]::Escape($definition) + '\s*$')) {
                throw "CoreMark preprocessing disagrees with the manifest: $definition"
            }
        }
        $seed1 = if ($RunMode -eq 'validation') { 0x3415 } else { 0 }
        $seed2 = $seed1
        $seedExpressions = [ordered]@{
            seed1_volatile = $(if ($RunMode -eq 'validation') { '0x3415' } else { '0' })
            seed2_volatile = $(if ($RunMode -eq 'validation') { '0x3415' } else { '0' })
            seed3_volatile = '0x66'
            seed4_volatile = [string]$Iterations
            seed5_volatile = '0'
        }
        $preprocessedPort = (& $gcc @compileFlags -E 'coremark_test_soc/sw/coremark/core_portme.c' | Out-String)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot verify preprocessed CoreMark seed initializers' }
        foreach ($seed in $seedExpressions.GetEnumerator()) {
            if ($preprocessedPort -notmatch ('\b' + [regex]::Escape($seed.Key) + '\s*=\s*' +
                [regex]::Escape($seed.Value) + '\s*;')) {
                throw "Preprocessed CoreMark seed differs: $($seed.Key)"
            }
        }
        [IO.File]::WriteAllText((Join-Path $outDir 'macros.txt'), $macros, $utf8)
        $bytes = [IO.File]::ReadAllBytes($bin)
        if ($bytes.Length -gt 131072) { throw 'Firmware exceeds 128 KiB BRAM' }
        $padded = [byte[]]::new(131072)
        [Array]::Copy($bytes, $padded, $bytes.Length)
        $words = [string[]]::new(32768)
        for ($word = 0; $word -lt $words.Length; $word++) {
            $words[$word] = [BitConverter]::ToUInt32($padded, $word * 4).ToString('x8')
        }
        [IO.File]::WriteAllText((Join-Path $outDir 'ram.hex'), ($words -join "`n") + "`n", $utf8)
        $fileHashes = [ordered]@{}
        foreach ($name in @('coremark.elf', 'coremark.bin', 'ram.hex', 'macros.txt', 'coremark_build_config.h')) {
            $fileHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $outDir $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $portableArguments = @($arguments | ForEach-Object {
            $_.Replace($libgcc, $portableLibgcc).Replace($outDir, '<output>').Replace($objectDir, '<objects>')
        })
        $manifest = [ordered]@{
            schema_version = 3
            purpose = 'RV32IMA CoreMark firmware; duration is validated from target mcycle ticks'
            evidence_class = $EvidenceClass
            isa = $variant; march = $march; abi = 'ilp32'
            iterations = $Iterations; cpu_hz = $CpuHz; coremark_sim = $false
            run_mode = $RunMode; tick_report = 'PORT_TICKS64'
            seeds = [ordered]@{ seed1 = $seed1; seed2 = $seed2; seed3 = 0x66;
                seed4 = $Iterations; seed5 = 0 }
            total_data_size_bytes = 2000
            coremark_upstream = $upstream.commit
            optimization = "-$Optimization"
            compiler = "GCC $version ($target)"
            compiler_version = $version; compiler_target = $target
            compiler_sha256 = (Get-FileHash -LiteralPath $gcc -Algorithm SHA256).Hash.ToLowerInvariant()
            compiler_flags = $reportedFlags
            compile_arguments = $compileCommands
            build_arguments = $portableArguments
            common_libgcc = [ordered]@{
                multilib = $multilib
                selected_by_march = $libraryMarch
                path = $portableLibgcc
                sha256 = (Get-FileHash -LiteralPath $libgcc -Algorithm SHA256).Hash.ToLowerInvariant()
                reason = 'Explicit compiler-selected RV32IMA/ILP32-compatible helpers; ELF32, soft-float and no-C checked'
            }
            image_bytes = $bytes.Length
            elf_text_bytes = [long]$sizeMatch.Groups[1].Value
            elf_data_bytes = [long]$sizeMatch.Groups[2].Value
            elf_bss_bytes = [long]$sizeMatch.Groups[3].Value
            compressed_instructions = $shortCount; word_instructions = $wordCount
            source_files = $sourceHashes; files = $fileHashes
        }
        [IO.File]::WriteAllText((Join-Path $outDir 'manifest.json'), ($manifest | ConvertTo-Json -Depth 8) + "`n", $utf8)
        Write-Output "$variant`: $($bytes.Length) image bytes; $shortCount compressed instructions; $outDir"
    }
} finally { $env:PATH = $savedPath; Pop-Location }
