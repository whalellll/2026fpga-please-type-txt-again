[CmdletBinding()]
param(
    [switch]$ValidateOnly,
    [switch]$VerifyWithPds,
    [switch]$Synthesize,
    [string]$PdsShell = '',
    [string]$PythonPath = '',
    [string]$StageRoot = '',
    [string]$FirmwareDirectory = '',
    [ValidateRange(1, 3600)][int]$TimeoutSeconds = 3600,
    [ValidatePattern('^$|^[0-9a-fA-F]{64}$')][string]$ExpectedCoreSha256 = '',
    [ValidateRange(1.0, 1000.0)][double]$CpuPeriodNs = 20.2020202
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pds = Join-Path $root 'coremark_test_soc/pds'
$projectPath = Join-Path $pds 'coremark_test_soc.pds'
$project = [IO.File]::ReadAllText($projectPath)
if (!$FirmwareDirectory) { $FirmwareDirectory = Join-Path $root 'coremark_test_soc/sim/coremark_ima' }
$FirmwareDirectory = [IO.Path]::GetFullPath($FirmwareDirectory)
& (Join-Path $PSScriptRoot 'verify_build_inputs.ps1') -GeneratedCpu -FirmwareDirectory $FirmwareDirectory

function Assert-RegularFile([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing input: $Path" }
    if ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Input must be a regular file: $Path"
    }
}
function Copy-Rom([string]$Source, [string]$Target) {
    $parent = Split-Path $Target -Parent
    $current = $parent
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and
            ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing linked ROM directory: $current"
        }
        $next = Split-Path $current -Parent
        if ($next -eq $current) { break }
        $current = $next
    }
    if (Test-Path -LiteralPath $Target) { Assert-RegularFile $Target }
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target -Force
}
function Prepare-Roms([string]$TreeRoot) {
    $treePds = Join-Path $TreeRoot 'coremark_test_soc/pds'
    Copy-Rom (Join-Path $FirmwareDirectory 'ram.hex') (Join-Path $treePds 'ram.hex')
    foreach ($prefix in @('coremark_test_soc/pds', 'coremark_test_soc/pds/work', 'generated/core')) {
        foreach ($name in @('zero_1024.hex', 'zero_2048.hex', 'zero_4096.hex')) {
            Copy-Rom (Join-Path $root "scripts/meminit/$name") (Join-Path $TreeRoot "$prefix/scripts/meminit/$name")
        }
    }
}

# This is also the fast regression for the original missing work/CoreTop.sv bug.
$inputs = @([regex]::Matches($project, '\(_file\s+"([^"]+)"') |
    ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
if ($inputs.Count -ne 5) { throw 'Expected CPU, three test-SoC RTL inputs and one FDC' }
foreach ($relative in $inputs) {
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '^[A-Za-z]:|\\|(^|/)work/') {
        throw "PDS input must use a portable source path, not generated work: $relative"
    }
    $resolved = [IO.Path]::GetFullPath((Join-Path $pds $relative))
    if (!$resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "PDS input escapes the project: $relative"
    }
    Assert-RegularFile $resolved
}
foreach ($marker in @('(_device PG2L100H)', '(_speedgrade -6)', '(_package FBG676)',
    '(_option top_module (_string "coremark_soc_top"))',
    '(_option selected_syn_tool_opt (_integer 2))')) {
    if (!$project.Contains($marker)) { throw "PDS configuration missing: $marker" }
}
foreach ($name in @('zero_1024.hex', 'zero_2048.hex', 'zero_4096.hex')) {
    Assert-RegularFile (Join-Path $root "scripts/meminit/$name")
}
$coreHash = (Get-FileHash -LiteralPath (Join-Path $root 'generated/core/CoreTop.sv') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedCoreSha256 -and $coreHash -ne $ExpectedCoreSha256.ToLowerInvariant()) {
    throw "Generated CPU differs from the requested input: actual=$coreHash expected=$ExpectedCoreSha256"
}
Assert-RegularFile (Join-Path $FirmwareDirectory 'manifest.json')
Assert-RegularFile (Join-Path $FirmwareDirectory 'ram.hex')
$firmwareManifestPath = Join-Path $FirmwareDirectory 'manifest.json'
$firmwareManifestText = [IO.File]::ReadAllText($firmwareManifestPath)
$firmware = $firmwareManifestText | ConvertFrom-Json
if ($firmware.isa -ne 'rv32ima' -or $firmware.march -ne 'rv32ima_zicsr_zifencei' -or
    $firmware.abi -ne 'ilp32' -or $firmware.compressed_instructions -ne 0 -or
    $firmware.compiler_target -ne 'riscv32-unknown-elf') {
    throw 'PDS requires RV32IMA/Zicsr/Zifencei, ILP32 and genuine riscv32-unknown-elf firmware.'
}
$ramHash = (Get-FileHash -LiteralPath (Join-Path $FirmwareDirectory 'ram.hex') -Algorithm SHA256).Hash.ToLowerInvariant()
if (!$firmware.files.'ram.hex' -or $ramHash -ne $firmware.files.'ram.hex') { throw 'Firmware ram.hex hash does not match manifest.json' }
$constraintText = [IO.File]::ReadAllText((Join-Path $pds 'coremark_test_soc.fdc'))
$clockMatch = [regex]::Match($constraintText, 'create_clock\s+-name\s+cpu_clk\s+-period\s+([0-9.]+)\s+\[get_ports\s+\{clk\}\]')
if (!$clockMatch.Success) { throw 'Missing explicit test-harness clk constraint' }
$sourcePeriod = [double]::Parse($clockMatch.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
if (!$firmware.cpu_hz -or [Math]::Abs(1.0e9 / $sourcePeriod - [double]$firmware.cpu_hz) -gt 1.0) {
    throw 'Committed PDS clock and selected firmware cpu_hz differ; rebuild firmware and synchronize the constraint'
}
if (!$ValidateOnly) { Prepare-Roms $root }
Write-Output "PDS_INPUTS_PASS sources=$($inputs.Count) ram_sha256=$ramHash"

if ($VerifyWithPds -or $Synthesize) {
    if (!$PdsShell -and $env:PDS_ROOT) { $PdsShell = Join-Path $env:PDS_ROOT 'bin/pds_shell.exe' }
    $localConfig = Join-Path $root 'toolchain.local.json'
    if (Test-Path -LiteralPath $localConfig) {
        $localSettings = Get-Content -LiteralPath $localConfig -Raw | ConvertFrom-Json
        if (!$PdsShell) { $PdsShell = $localSettings.PdsShell }
        if (!$StageRoot) { $StageRoot = $localSettings.PdsStageRoot }
        if (!$PythonPath) { $PythonPath = $localSettings.PythonPath }
    }
    if (!$PdsShell) { throw 'Pass -PdsShell, set PDS_ROOT, or configure toolchain.local.json' }
    Assert-RegularFile $PdsShell
    if (@(Get-Process -Name pds,pds_shell -ErrorAction SilentlyContinue).Count) {
        throw 'Close or finish the existing PDS GUI/script before starting this check'
    }
    $logRoot = Join-Path $root 'work/logs/pds-coremark'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    if ($Synthesize) {
        . (Join-Path $PSScriptRoot 'pds_control_audit.ps1')
        $PythonPath = Resolve-PdsAuditPython -PythonPath $PythonPath -LogDirectory (Join-Path $logRoot 'prerequisites')
    }
    if (!$StageRoot) { $StageRoot = [IO.Path]::GetTempPath() }
    $StageRoot = [IO.Path]::GetFullPath($StageRoot).TrimEnd('\')
    if ($StageRoot -match '[^\x20-\x7E]') { throw 'Use an ASCII -StageRoot (or config.PdsStageRoot) for PDS staging' }
    $stage = Join-Path $StageRoot ('cpu_pds_' + [guid]::NewGuid().ToString('N'))
    $checkout = Join-Path $stage 'portable checkout'
    $checkPds = Join-Path $checkout 'coremark_test_soc/pds'
    New-Item -ItemType Directory -Path $checkPds -Force | Out-Null
    Copy-Item -LiteralPath $projectPath -Destination $checkPds
    foreach ($relative in $inputs) {
        $source = [IO.Path]::GetFullPath((Join-Path $pds $relative))
        $target = [IO.Path]::GetFullPath((Join-Path $checkPds $relative))
        if (!$target.StartsWith($checkout + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Staging path escaped its root' }
        Copy-Rom $source $target
    }
    Prepare-Roms $checkout
    if ($Synthesize) {
        $auditSource = Join-Path $PSScriptRoot 'audit_pds_controls.py'
        $auditHash = (Get-FileHash -LiteralPath $auditSource -Algorithm SHA256).Hash.ToLowerInvariant()
        $stagedAudit = Join-Path $checkout 'scripts/audit_pds_controls.py'
        Copy-Rom $auditSource $stagedAudit
        if ((Get-FileHash -LiteralPath $stagedAudit -Algorithm SHA256).Hash.ToLowerInvariant() -ne $auditHash) {
            throw 'ADS auditor changed while preparing the isolated copy'
        }
        $periodText = $CpuPeriodNs.ToString('0.########', [Globalization.CultureInfo]::InvariantCulture)
        [IO.File]::WriteAllText((Join-Path $checkPds 'coremark_test_soc.fdc'),
            "# Synthesis experiment only; external test-harness clock, no board pin claims.`ncreate_clock -name cpu_clk -period $periodText [get_ports {clk}]`n")
    }
    $process = New-Object Diagnostics.Process
    $process.StartInfo.FileName = $PdsShell
    $process.StartInfo.WorkingDirectory = $checkPds
    $process.StartInfo.Arguments = '-work_dir "' + $checkPds + '"'
    if ($Synthesize) {
        $process.StartInfo.Arguments += ' -project "' + (Join-Path $checkPds 'coremark_test_soc.pds') + '" -run synthesize'
    }
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardInput = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $limit = if ($Synthesize) { $TimeoutSeconds } else { 30 }
    Write-Output "PDS_CHECK: isolated source/ROM copy; limit ${limit}s. Timeout stops this process tree; Ctrl+C can be delayed while PDS is being waited on. Stage: $checkout"
    $label = if ($Synthesize) { 'synthesis' } else { 'open' }
    $attemptRoot = Join-Path $logRoot ([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + $label + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $attemptRoot -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $attemptRoot 'firmware-manifest.json'), $firmwareManifestText)
    $evidence = [ordered]@{
        check = $label; startedUtc = [DateTime]::UtcNow.ToString('o'); completedUtc = $null; status = 'RUNNING'
        sourceRoot = $root; stage = $checkout; attemptLogDirectory = $attemptRoot
        top = 'coremark_soc_top'; scope = 'CPU test harness; no board/P&R/frequency claim'
        timeoutSeconds = $limit; cpuPeriodNs = $CpuPeriodNs; firmwareRamSha256 = $ramHash; pdsShell = $PdsShell
        firmwareManifestSha256 = (Get-FileHash -LiteralPath (Join-Path $attemptRoot 'firmware-manifest.json')).Hash.ToLowerInvariant()
        coreSha256 = (Get-FileHash -LiteralPath (Join-Path $checkout 'generated/core/CoreTop.sv')).Hash.ToLowerInvariant()
        effectiveConstraintSha256 = (Get-FileHash -LiteralPath (Join-Path $checkPds 'coremark_test_soc.fdc')).Hash.ToLowerInvariant()
        inputs = @(@($projectPath) + @($inputs | ForEach-Object { [IO.Path]::GetFullPath((Join-Path $pds $_)) }) |
            ForEach-Object { [ordered]@{ path = $_.Substring($root.Length + 1).Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $_).Hash.ToLowerInvariant() } })
        meminit = @('zero_1024.hex', 'zero_2048.hex', 'zero_4096.hex') | ForEach-Object {
            [ordered]@{ path = "scripts/meminit/$_"; sha256 = (Get-FileHash -LiteralPath (Join-Path $checkout "generated/core/scripts/meminit/$_")).Hash.ToLowerInvariant() }
        }
    }
    if ($evidence.coreSha256 -ne $coreHash) { throw 'Generated CPU changed while preparing the isolated copy' }
    if ((Get-FileHash -LiteralPath (Join-Path $checkPds 'ram.hex')).Hash.ToLowerInvariant() -ne $ramHash) {
        throw 'Firmware changed while preparing the isolated copy'
    }
    if ($Synthesize) {
        $evidence.adsAuditPythonPath = $PythonPath
        $evidence.adsAuditGateScriptSha256 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'pds_control_audit.ps1')).Hash.ToLowerInvariant()
        $evidence.adsControls = [ordered]@{
            status = 'PENDING'; auditScriptSha256 = $auditHash; pythonPath = $PythonPath
        }
    }
    function Save-Evidence {
        $json = $evidence | ConvertTo-Json -Depth 6
        $json | Set-Content -LiteralPath (Join-Path $attemptRoot "$label.json") -Encoding UTF8
        $json | Set-Content -LiteralPath (Join-Path $logRoot "$label.json") -Encoding UTF8
    }
    function Save-Output([string]$Text) {
        [IO.File]::WriteAllText((Join-Path $attemptRoot "$label.log"), $Text)
        [IO.File]::WriteAllText((Join-Path $logRoot "$label.log"), $Text)
    }
    Save-Evidence
    $started = $false
    try {
        [void]$process.Start()
        $started = $true
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $openPath = (Join-Path $checkPds 'coremark_test_soc.pds').Replace('\', '/')
        if (!$Synthesize) {
            $process.StandardInput.WriteLine('open_project "' + $openPath + '"')
            $process.StandardInput.WriteLine('exit')
        }
        $process.StandardInput.Close()
        if (!$process.WaitForExit($limit * 1000)) {
            $evidence.status = 'TIMEOUT'
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            if ($process.WaitForExit(5000)) {
                Save-Output ($stdout.Result + "`n" + $stderr.Result)
            }
            throw "PDS $label exceeded ${limit}s; its process tree was stopped"
        }
        $outputText = $stdout.Result + "`n" + $stderr.Result
        Save-Output $outputText
        if ($process.ExitCode -ne 0 -or $outputText -match '(?im)^\s*E:|Program Error Out|Parsing ERROR|Cannot open specified data file') {
            throw "PDS $label failed; inspect work/logs/pds-coremark/$label.log"
        }
        if ($Synthesize) {
            if ($outputText -notmatch 'Process "Synthesize" done\.') { throw 'PDS synthesis completion marker missing' }
            $reports = @(Get-ChildItem -LiteralPath $checkPds -Filter '*.snr' -Recurse)
            if (!$reports.Count) { throw 'Synthesis report missing' }
            $netlists = @(Get-ChildItem -LiteralPath $checkPds -Filter '*_syn.vm' -Recurse | Where-Object Length -gt 100)
            if ($netlists.Count -ne 1 -or $netlists[0].Name -ne 'coremark_soc_top_syn.vm') {
                throw 'Expected exactly one coremark_soc_top ADS synthesis netlist'
            }
            foreach ($report in $reports) { Copy-Item -LiteralPath $report.FullName -Destination $attemptRoot -Force }
            $evidence.netlists = @($netlists | ForEach-Object { [ordered]@{ path = $_.FullName; sha256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() } })
            $evidence.adsControls.status = 'RUNNING'
            Save-Evidence
            Write-Output 'PDS_ADS_CONTROLS: checking branch selectors, PMA windows and RsMem refresh guard; limit 300s.'
            $evidence.adsControls = Invoke-PdsControlAudit -PythonPath $PythonPath -AuditScript $stagedAudit `
                -Netlist $netlists[0].FullName -OutputPath (Join-Path $attemptRoot 'ads-controls.json') `
                -ExpectedAuditSha256 $auditHash
        } elseif ($outputText -notmatch '(?s)Executing : open_project \{?.*coremark_test_soc\.pds\}?\s+successfully\.') {
            throw 'PDS project-open success marker missing'
        }
        $evidence.status = 'PASS'
        $evidence.completedUtc = [DateTime]::UtcNow.ToString('o')
        Save-Evidence
        Write-Output "PDS_PORTABLE_COPY_$($label.ToUpperInvariant())_PASS"
    } catch {
        if ($Synthesize -and $evidence.adsControls.status -eq 'RUNNING') { $evidence.adsControls.status = 'ERROR' }
        if ($evidence.status -eq 'RUNNING') { $evidence.status = 'ERROR' }
        $evidence.completedUtc = [DateTime]::UtcNow.ToString('o')
        $evidence.error = $_.Exception.Message
        Save-Evidence
        throw
    } finally {
        if ($started -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
        $process.Dispose()
        if ($Synthesize) {
            # Keep the isolated ADS netlist/report tree for inspection, outside Git.
            Write-Output "PDS_STAGE_RETAINED: $checkout"
        } else {
            $resolvedStage = [IO.Path]::GetFullPath($stage)
            if (!$resolvedStage.StartsWith($StageRoot + '\cpu_pds_', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Refusing to remove a stage outside the owned temporary directory'
            }
            $stageEntries = @(Get-Item -LiteralPath $resolvedStage -Force) + @(Get-ChildItem -LiteralPath $resolvedStage -Force -Recurse)
            if (@($stageEntries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
                throw 'Refusing to remove a temporary stage containing links'
            }
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force
        }
    }
}
if (!$ValidateOnly) { Write-Output "PDS_GUI_READY: $projectPath" }
