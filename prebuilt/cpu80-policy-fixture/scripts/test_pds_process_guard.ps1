param([switch]$CheckLive)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'start_detached_release_job.ps1'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
# Import only the three read-only guard functions, never the launcher's actions.
foreach ($name in @('Resolve-PdsGuardPath','Get-PdsProcessGuardDecision','Assert-PdsProcessAvailability')) {
    $definitions = @($ast.FindAll({param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true))
    if ($definitions.Count -ne 1) { throw "Expected one guard function: $name" }
    . ([scriptblock]::Create($definitions[0].Extent.Text))
}
$fixture = Join-Path $root ('artifacts/selftest/pds_process_guard/' + [guid]::NewGuid().ToString('N'))
$repo = Join-Path $fixture 'repository'
$foreign = Join-Path $fixture 'foreign/pds'
New-Item -ItemType Directory -Path (Join-Path $repo 'pds'), $foreign | Out-Null
$foreignProject = Join-Path $foreign 'soc_gui.pds'
$sameProject = Join-Path $repo 'pds/soc_gui.pds'
$normal = '(_project (_option prj_work_dir (_string ".")) (_option prj_impl_dir (_string ".")))'
[IO.File]::WriteAllText($foreignProject, $normal)
[IO.File]::WriteAllText($sameProject, $normal)
$base = [ordered]@{process_id=1708; name='pds.exe'; stable=$true; responding=$true
    cpu_delta_ticks=0; child_ids=@(); command_line='"C:\tools\pds.exe" -project "' + $foreignProject + '"'
    window_title='Pango Design Suite 2022.2-SP6.4 - ' + $foreignProject.Replace('\','/') + ' (on fixture-host)'}
$results = [Collections.Generic.List[object]]::new()
function Check-Decision([string]$Name, [hashtable]$Changes, [bool]$Allowed) {
    $evidence = [ordered]@{}
    foreach ($key in $base.Keys) { $evidence[$key] = $base[$key] }
    foreach ($key in $Changes.Keys) { $evidence[$key] = $Changes[$key] }
    $decision = Get-PdsProcessGuardDecision $repo $evidence
    if ($decision.allowed -ne $Allowed) { throw "Fixture $Name mismatch: $($decision | ConvertTo-Json -Compress)" }
    $results.Add([ordered]@{name=$Name; expected_allowed=$Allowed; decision=$decision})
}
Check-Decision 'distinct-idle-gui' @{} $true
Check-Decision 'same-repository-gui' @{
    command_line='pds.exe -project "'+$sameProject+'"'
    window_title='Pango Design Suite 2022.2-SP6.4 - '+$sameProject+' (on fixture-host)'
} $false
Check-Decision 'cli-always-blocks' @{name='pds_shell.exe'} $false
Check-Decision 'unknown-command-line' @{command_line='pds.exe'} $false
Check-Decision 'unknown-window-title' @{window_title='Pango Design Suite'} $false
Check-Decision 'switched-project-title' @{window_title='Pango Design Suite 2022.2-SP6.4 - '+$sameProject+' (on fixture-host)'} $false
Check-Decision 'child-engine-active' @{child_ids=@(200)} $false
Check-Decision 'isolated-gui-cpu-alone-does-not-prove-compiler' @{cpu_delta_ticks=312500} $true
Check-Decision 'gui-unresponsive' @{responding=$false} $false
Check-Decision 'pid-or-title-changed' @{stable=$false} $false
Check-Decision 'sampling-unavailable' @{stable=$false; cpu_delta_ticks=-1} $false
Check-Decision 'relative-project-unknown' @{
    command_line='pds.exe -project "soc_gui.pds"'
    window_title='Pango Design Suite 2022.2-SP6.4 - soc_gui.pds (on fixture-host)'
} $false
foreach ($option in @('prj_work_dir','prj_impl_dir')) {
    [IO.File]::WriteAllText($foreignProject, $normal.Replace('(_option '+$option+' (_string "."))',
        '(_option '+$option+' (_string "'+$repo+'"))'))
    Check-Decision "overlapping-$option" @{} $false
}
[IO.File]::WriteAllText($foreignProject, '(_project (_option prj_work_dir (_string ".")))')
Check-Decision 'missing-implementation-dir' @{} $false
[IO.File]::WriteAllText($foreignProject, $normal + ' (_option prj_work_dir (_string "."))')
Check-Decision 'ambiguous-work-dir' @{} $false
[IO.File]::WriteAllText($foreignProject, $normal)
$report = [ordered]@{status='PASS'; kind='PDS_GUARD_FIXTURES_NO_PDS_LAUNCH'; tests=$results.Count
    launcher_sha256=(Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToLowerInvariant()
    results=@($results.ToArray()); live_check=$null}
if ($CheckLive) { $report.live_check = Assert-PdsProcessAvailability $root }
$output = Join-Path $fixture 'result.json'
[IO.File]::WriteAllText($output, ($report | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "PDS_PROCESS_GUARD_FIXTURES_PASS tests=$($results.Count) result=$output"
