<#
.SYNOPSIS
Build a full bootloader in a fresh isolated directory, keeping its 16 KiB stack gate.
.DESCRIPTION
Only the copied compiler-version expectation and CoreMark optimization/reporting
configuration change. Production sources, defaults and artifacts are untouched.
O2/O3 apply to all six CoreMark translation units. No simulation or PDS runs.
PrepareOnly copies and checks inputs without invoking the compiler. A failed
stack assertion is recorded as REJECTED_CAPACITY, never as a passing image.
.EXAMPLE
.\scripts\test_compiler_capacity.ps1 -ToolchainRoot C:\tools\gcc16 -ExpectedGccVersion 16.2.0 -CoreMarkOptimization O2 -OutputDirectory C:\results\gcc16-O2
.EXAMPLE
.\scripts\run_coremark_integration_test.ps1 -ToolchainRoot C:\tools\gcc16 -ExpectedGccVersion 16.2.0 -CoreMarkOptimization O2 -WorkloadLayout bootloader -CapacityEvidence C:\results\gcc16-O2\capacity.json
#>
param(
    [string]$ToolchainRoot = '',
    [ValidateSet('14.2.0','16.2.0')][string]$ExpectedGccVersion = '16.2.0',
    [ValidateSet('O2','O3')][string]$CoreMarkOptimization = 'O2',
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateRange(30,600)][int]$TimeoutSeconds = 180,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'compiler_capacity_helpers.ps1')
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$out = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $out) { throw 'OutputDirectory must be new; previous candidate evidence is never overwritten.' }
$originalPath = $env:PATH
try {
    $sourceFiles = Get-CompilerCapacityInputs -Root $root
    Assert-CpuCoremarkSources -Directory (Join-Path $root 'sw/coremark')
    $project = Join-Path $out 'project'
    foreach ($name in $sourceFiles.Keys) {
        $destination = Join-Path $project $name
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $destination
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceFiles[$name]) {
            throw "Input changed while copying: $name"
        }
    }
    New-Item -ItemType Directory -Path (Join-Path $project 'pds') -Force | Out-Null
    $utf8 = [Text.UTF8Encoding]::new($false)
    $builder = Join-Path $project 'scripts/build_bootloader.ps1'
    $body = [IO.File]::ReadAllText($builder)
    $oldVersion = '$toolchain=Get-CpuToolchain -ToolchainRoot $ToolchainRoot'
    $oldArgs = "`$coreArgs=`$common+@('-O2','-I',`$core)+`$definitions+@('-c',`$source,'-o',`$object)"
    $oldReport = "CoreMark/camera/CRC/PNG -O2; other bootloader code -Os; bootloader LTO"
    foreach ($needle in @($oldVersion,$oldArgs,$oldReport)) {
        if ([regex]::Matches($body,[regex]::Escape($needle)).Count -ne 1) {
            throw 'Production builder changed; review the isolated candidate adaptation before proceeding.'
        }
    }
    $body = $body.Replace($oldVersion, "`$CpuGccVersion='$ExpectedGccVersion'`r`n$oldVersion")
    $newArgs = "`$coreArgs=`$common+@('-$CoreMarkOptimization','-include',(Join-Path `$PSScriptRoot 'candidate_config.h'),'-I',`$core)+`$definitions+@('-c',`$source,'-o',`$object)"
    $body = $body.Replace($oldArgs,$newArgs).Replace($oldReport,"CoreMark -$CoreMarkOptimization; camera/CRC/PNG -O2; other bootloader code -Os; bootloader LTO")
    [IO.File]::WriteAllText($builder,$body,$utf8)
    $config = '#define COMPILER_FLAGS "-' + $CoreMarkOptimization + ' -march=' + $CpuMarch + ' -mabi=' + $CpuAbi + '"'
    [IO.File]::WriteAllText((Join-Path $project 'scripts/candidate_config.h'),$config + "`n",$utf8)
    $copyInputs = Get-CompilerCapacityInputs -Root $project
    $copyInputs['scripts/candidate_config.h'] = (Get-FileHash -LiteralPath (Join-Path $project 'scripts/candidate_config.h') -Algorithm SHA256).Hash.ToLowerInvariant()
    $record = [ordered]@{
        schema_version = 1
        kind = 'full_bootloader_compiler_capacity'
        result = 'PREPARED_ONLY'
        scope = 'Full production bootloader capacity and linked ISA check; no CPU simulation, score or board validation.'
        coremark_optimization = $CoreMarkOptimization
        expected_compiler_version = $ExpectedGccVersion
        source_files = $sourceFiles
        isolated_input_files = $copyInputs
        isolated_recipe_changes = @('Expected compiler version (local only)',"All six CoreMark translation units -$CoreMarkOptimization",'Matching COMPILER_FLAGS via forced header')
        original_stack_gate = '__bss_end < __stack_top - 16384 (unchanged)'
        invocation = "test_compiler_capacity.ps1 -ExpectedGccVersion $ExpectedGccVersion -CoreMarkOptimization $CoreMarkOptimization -ToolchainRoot <verified root> -OutputDirectory <new directory>"
        runner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        helper_sha256 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'compiler_capacity_helpers.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if (!$PrepareOnly) {
        $CpuGccVersion = $ExpectedGccVersion
        $toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
        $record.compiler = [ordered]@{
            target = $toolchain.Target; version = $toolchain.Version
            sha256 = (Get-FileHash -LiteralPath $toolchain.gcc -Algorithm SHA256).Hash.ToLowerInvariant()
            libgcc_selected_by = "-march=$($toolchain.LibgccMarch) -mabi=ilp32 -print-libgcc-file-name"
            libgcc_sha256 = $toolchain.LibgccSha256; libgcc_metadata = $toolchain.LibgccMetadata
        }
        if (!('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs') }
        $log = Join-Path $out 'build.stdout.txt'; $err = Join-Path $out 'build.stderr.txt'
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $builder + '" -ToolchainRoot "' + $toolchain.Root + '"'
        Write-Host "Full image candidate build: owner PID=$PID, limit=$TimeoutSeconds seconds. Stopping this owner terminates its build descendants."
        $exitCode = [CpuSimulation.BoundedProcess]::Run((Join-Path $PSHOME 'powershell.exe'),$arguments,$project,$log,$err,$TimeoutSeconds)
        $map = Join-Path $project 'artifacts/bootloader.map'
        $layout = Get-BootloaderCapacityLayout -Map $map
        $outputText = [IO.File]::ReadAllText($log) + [IO.File]::ReadAllText($err)
        if ($exitCode -ne 0) {
            if ($layout.stack_gate_passed -or $outputText -notmatch 'bootloader leaves less than 16 KiB stack' -or
                $outputText -notmatch 'GCC link failed' -or $outputText -match 'undefined reference|cannot find|unrecognized|internal compiler error') {
                throw "Candidate build failed for a reason other than the preserved capacity gate; see $err"
            }
            $record.result = 'REJECTED_CAPACITY'
        } else {
            if (!$layout.stack_gate_passed -or $outputText -notmatch 'Bootloader built:') { throw 'Missing completed bootloader build and stack-gate success.' }
            $record.result = 'PASS'
            $record.firmware = Get-Content -LiteralPath (Join-Path $project 'artifacts/bootloader.build.json') -Raw | ConvertFrom-Json
        }
        $record.layout = $layout
        $record.build_exit_code = $exitCode
        $record.outputs = [ordered]@{}
        foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $project 'artifacts') -File -Recurse | Sort-Object FullName)) {
            $name = $file.FullName.Substring($out.TrimEnd('\','/').Length + 1).Replace('\','/')
            $record.outputs[$name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        foreach ($name in @('build.stdout.txt','build.stderr.txt')) {
            $record.outputs[$name] = (Get-FileHash -LiteralPath (Join-Path $out $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $after = Get-CompilerCapacityInputs -Root $root
    if ($after.Count -ne $sourceFiles.Count) { throw 'Production source set changed during candidate check.' }
    foreach ($name in $sourceFiles.Keys) {
        if ($after[$name] -ne $sourceFiles[$name]) { throw "Production source changed during candidate check: $name" }
    }
    foreach ($name in $copyInputs.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $project $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $copyInputs[$name]) {
            throw "Isolated build input changed during execution: $name"
        }
    }
    [IO.File]::WriteAllText((Join-Path $out 'capacity.json'),($record | ConvertTo-Json -Depth 15) + "`n",$utf8)
    Write-Output "COMPILER_CAPACITY_$($record.result) gcc=$ExpectedGccVersion core=$CoreMarkOptimization evidence=$out\capacity.json"
} finally { $env:PATH = $originalPath }
