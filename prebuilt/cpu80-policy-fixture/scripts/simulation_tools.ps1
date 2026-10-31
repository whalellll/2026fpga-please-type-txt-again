# current CPU uses packed-array selection that Icarus cannot elaborate. Run the
# unchanged generated SystemVerilog with Verilator; retain bounded logs only.
function ConvertTo-MsysPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).Replace('\','/')
    if ($full -notmatch '^[A-Za-z]:/') { throw "Expected a local Windows path: $Path" }
    return '/' + $full.Substring(0,1).ToLowerInvariant() + $full.Substring(2)
}
function Quote-BashArgument([string]$Value) {
    return "'" + $Value.Replace("'", "'" + [char]34 + "'" + [char]34 + "'") + "'"
}
function Invoke-BoundedProcess {
    param([string]$Executable, [string]$Arguments, [string]$Directory,
          [string]$Log, [int]$TimeoutSeconds)
    $err = $Log + '.stderr.log'
    if (!('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
    }
    try {
        $exitCode = [CpuSimulation.BoundedProcess]::Run(
            $Executable, $Arguments, $Directory, $Log, $err, $TimeoutSeconds)
    } catch {
        throw "Bounded process stopped, including its job descendants: $Executable; $($_.Exception.GetBaseException().Message)"
    }
    $text = [IO.File]::ReadAllText($Log) + [IO.File]::ReadAllText($err)
    if ($exitCode -ne 0 -or $text -match '(?im)^(ERROR|FATAL|%Error):') {
        Write-Host (($text -split "`n" | Select-Object -Last 35) -join "`n")
        throw "Process failed: $Executable (exit $exitCode); see $Log"
    }
    return $text
}
function Build-VerilatorModel {
    param([string]$Root, [string]$Top, [string[]]$Sources,
          [string]$MsysRoot = 'D:\LJL\WORK\msys64', [int]$TimeoutSeconds = 1200,
          [ValidateRange(1,2)][int]$BuildJobs = 2,
          [string]$ModelDirectory = '')
    $env:PATH = (Join-Path $MsysRoot 'mingw64/bin') + ';' + $env:PATH
    $directory = if ($ModelDirectory) { [IO.Path]::GetFullPath($ModelDirectory) } else {
        Join-Path $Root "artifacts/selftest/verilator_$Top"
    }
    if ($ModelDirectory -and (Test-Path -LiteralPath $directory)) {
        throw "Fresh Verilator model directory already exists: $directory"
    }
    $executable = Join-Path $directory "V$Top.exe"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $sourceHashes = [ordered]@{}
    foreach ($name in $Sources) {
        $path = if ([IO.Path]::IsPathRooted($name)) { $name } else { Join-Path $Root $name }
        $sourceHashes[$name] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $options = @('--binary','--timing','-CFLAGS','-Os','-CFLAGS','-fno-declone-ctor-dtor',
        '-Wno-fatal','-Wno-TIMESCALEMOD','-Wno-WIDTHEXPAND','-Wno-WIDTHTRUNC')
    $scriptPath = Join-Path $directory 'build.sh'
    $sourceArgs = @($Sources | ForEach-Object {
        $sourcePath = if ([IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $Root $_ }
        Quote-BashArgument (ConvertTo-MsysPath $sourcePath)
    })
    # Recent Verilator versions make -j also group all C++ into that many
    # translation units. Keep independent files when supported, without
    # passing an unknown option to older installations.
    $groupOptions = @'
task_verilator_help="$(verilator --help 2>/dev/null || true)"
task_group_args=()
if [[ "$task_verilator_help" == *"--output-groups"* ]]; then
    task_group_args=(--output-groups 0)
fi
'@
    $body = "#!/usr/bin/env bash`nset -euo pipefail`nexport PATH=/mingw64/bin:/usr/bin:`$PATH`n" +
        $groupOptions + "`n" +
        'cd ' + (Quote-BashArgument (ConvertTo-MsysPath $Root)) + "`n" +
        'verilator --binary --timing "${task_group_args[@]}" -CFLAGS ' +
        (Quote-BashArgument '-Os') + ' -CFLAGS ' +
        (Quote-BashArgument '-fno-declone-ctor-dtor') +
        ' -Wno-fatal -Wno-TIMESCALEMOD -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC' +
        ' --top-module ' + (Quote-BashArgument $Top) + ' --Mdir ' +
        (Quote-BashArgument (ConvertTo-MsysPath $directory)) + ' -j ' + $BuildJobs + ' ' + ($sourceArgs -join ' ') + "`n"
    [IO.File]::WriteAllText($scriptPath, $body, [Text.UTF8Encoding]::new($false))
    $log = Join-Path $directory 'build.log'
    $bashArgs = '--noprofile --norc "' + (ConvertTo-MsysPath $scriptPath) + '"'
    $buildOutput = Invoke-BoundedProcess -Executable (Join-Path $MsysRoot 'usr/bin/bash.exe') `
        -Arguments $bashArgs -Directory $Root -Log $log -TimeoutSeconds $TimeoutSeconds
    $executable = Join-Path $directory "V$Top.exe"
    if (!(Test-Path -LiteralPath $executable -PathType Leaf)) { throw "Missing Verilator executable: $executable" }
    foreach ($name in $Sources) {
        $path = if ([IO.Path]::IsPathRooted($name)) { $name } else { Join-Path $Root $name }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHashes[$name]) {
            throw "Model source changed during build: $name"
        }
    }
    $makefile = Join-Path $directory "V$Top.mk"
    $verilatedMk = Join-Path $MsysRoot 'mingw64/share/verilator/include/verilated.mk'
    if (!(Test-Path -LiteralPath $makefile -PathType Leaf) -or
        !(Test-Path -LiteralPath $verilatedMk -PathType Leaf)) {
        throw 'Missing generated Makefile or installed Verilator compilation rules'
    }
    $makeText = [IO.File]::ReadAllText($makefile)
    $rootMatches = [regex]::Matches($makeText, '(?m)^VERILATOR_ROOT\s*=\s*(\S+)\s*$')
    $expectedKit = ([IO.Path]::GetFullPath((Join-Path $MsysRoot 'mingw64/share/verilator'))).Replace('\','/').TrimEnd('/')
    if ($rootMatches.Count -ne 1 -or
        !$rootMatches[0].Groups[1].Value.Replace('\','/').TrimEnd('/').Equals($expectedKit,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Generated Makefile uses a different Verilator installation'
    }
    $userFlags = [regex]::Match($makeText, '(?ms)^VM_USER_CFLAGS\s*=.*?(?=^# User LDLIBS)')
    if (!$userFlags.Success -or $userFlags.Value -cnotmatch '(?m)^\s*-Os\s*\\?\s*$') {
        throw 'Generated Makefile does not contain the explicit host -Os override'
    }
    $compileLines = @($buildOutput -split "`r?`n" | Where-Object {
        $_ -match '(?i)(?:^|\s)\S*(?:g\+\+|clang\+\+|c\+\+)(?:\.exe)?\s' -and
        $_ -match '(?:^|\s)-c(?:\s|$)' -and $_ -match '\.cpp(?:\s|$)'
    })
    if ($ModelDirectory -and !$compileLines.Count) {
        throw 'Fresh Verilator model build emitted no C++ compiler commands'
    }
    foreach ($line in $compileLines) {
        $optimizations = @([regex]::Matches($line, '(?<!\S)-O(?:[0-3sgz]|fast)?(?=\s|$)') |
            ForEach-Object { $_.Value })
        if (!$optimizations.Count -or $optimizations[-1] -cne '-Os') {
            throw "Host C++ command did not end with the requested -Os optimization: $line"
        }
    }
    $record = [ordered]@{
        schema_version = 2; kind = 'verilator_explicit_host_os_model'; top = $Top
        elaboration_options = $options; rtl_defines = @(); rtl_parameters = @{}
        source_order = $Sources; source_files = $sourceHashes; host_build_jobs = $BuildJobs
        build_script_sha256 = (Get-FileHash -LiteralPath $scriptPath -Algorithm SHA256).Hash.ToLowerInvariant()
        model_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
        host_cpp = [ordered]@{
            explicit_cflags = '-Os'
            gcc16_mingw_ctor_workaround = '-fno-declone-ctor-dtor'
            compiler_argv_observed = ($compileLines.Count -gt 0)
            compile_command_count = $compileLines.Count
            compile_commands = $compileLines
            final_optimization_per_observed_command = '-Os'
            generated_makefile_sha256 = (Get-FileHash -LiteralPath $makefile -Algorithm SHA256).Hash.ToLowerInvariant()
            verilated_mk_sha256 = (Get-FileHash -LiteralPath $verilatedMk -Algorithm SHA256).Hash.ToLowerInvariant()
            build_log_sha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        runtime_inputs = 'ROM/plusargs are supplied at execution; no RTL defines or parameter overrides. Console timer acceleration is a runtime plusarg branch in the testbench, never a build parameter.'
    }
    [IO.File]::WriteAllText((Join-Path $directory 'model.json'),($record | ConvertTo-Json -Depth 8) + "`n",[Text.UTF8Encoding]::new($false))
    return $executable
}
function Invoke-SimulationCase {
    param([string]$Executable, [string]$Root, [string]$Name,
          [string]$Arguments = '', [string]$Marker, [int]$TimeoutSeconds = 180)
    $log = Join-Path $Root "artifacts/selftest/$Name.log"
    $result = Invoke-BoundedProcess -Executable $Executable -Arguments $Arguments `
        -Directory $Root -Log $log -TimeoutSeconds $TimeoutSeconds
    if (!$result.Contains($Marker)) { throw "Missing simulation result $Marker; see $log" }
    Write-Host (($result -split "`n" | Where-Object { $_ -match 'PASS' }) -join "`n")
}
