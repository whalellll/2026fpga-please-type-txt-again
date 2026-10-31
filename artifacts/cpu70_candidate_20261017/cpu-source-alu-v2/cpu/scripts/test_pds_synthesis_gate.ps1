[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Netlist,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$OutputPath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'pds_control_audit.ps1')
$Netlist = [IO.Path]::GetFullPath($Netlist)
$originalHash = (Get-FileHash -LiteralPath $Netlist -Algorithm SHA256).Hash.ToLowerInvariant()
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$work = Join-Path $root ('work/pds-gate-fixtures/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
if (!$OutputPath) { $OutputPath = Join-Path $work 'result.json' }
$PythonPath = Resolve-PdsAuditPython -PythonPath $PythonPath -LogDirectory $work
$auditor = Join-Path $PSScriptRoot 'audit_pds_controls.py'
$auditHash = (Get-FileHash -LiteralPath $auditor -Algorithm SHA256).Hash.ToLowerInvariant()
$helper = Join-Path $PSScriptRoot 'pds_control_audit.ps1'
# The child calls the same gate function used by PdsSynthesis. A gate exception
# must reach the caller as exit 1 before the success marker can be printed.
$child = Join-Path $work 'gate-child.ps1'
@'
param($Helper, $PythonPath, $Auditor, $Netlist, $OutputPath, $AuditHash)
$ErrorActionPreference = 'Stop'
. $Helper
$null = Invoke-PdsControlAudit -PythonPath $PythonPath -AuditScript $Auditor -Netlist $Netlist -OutputPath $OutputPath -ExpectedAuditSha256 $AuditHash
Write-Output 'PDS_ADS_GATE_PASS'
'@ | Set-Content -LiteralPath $child -Encoding UTF8
$mutator = Join-Path $work 'mutate.py'
@'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from test_pds_controls import change_init
source = Path(sys.argv[2]).read_bytes().decode('utf-8')
Path(sys.argv[3]).write_bytes(change_init(source, 'CoreFrontend', 'branch0', 0).encode('utf-8'))
'@ | Set-Content -LiteralPath $mutator -Encoding UTF8
$mutant = Join-Path $work 'branch0-zero.vm'
$code = [CpuSimulation.BoundedProcess]::Run($PythonPath,
    ('"' + $mutator + '" "' + $PSScriptRoot + '" "' + $Netlist + '" "' + $mutant + '"'),
    $work, (Join-Path $work 'mutator.stdout.log'), (Join-Path $work 'mutator.stderr.log'), 30)
if ($code -ne 0) { throw 'Could not prepare the reviewed branch0 mutation' }
$results = @()
$powershell = Join-Path $PSHOME 'powershell.exe'
foreach ($case in @('actual_netlist', 'branch0_constant_zero')) {
    $inputPath = if ($case -eq 'actual_netlist') { $Netlist } else { $mutant }
    $report = Join-Path $work ($case + '.json')
    $stdout = Join-Path $work ($case + '.stdout.log')
    $stderr = Join-Path $work ($case + '.stderr.log')
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $child + '" -Helper "' + $helper +
        '" -PythonPath "' + $PythonPath + '" -Auditor "' + $auditor + '" -Netlist "' + $inputPath +
        '" -OutputPath "' + $report + '" -AuditHash ' + $auditHash
    $exitCode = [CpuSimulation.BoundedProcess]::Run($powershell, $arguments, $work, $stdout, $stderr, 330)
    $text = [IO.File]::ReadAllText($stdout)
    $detail = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($case -eq 'actual_netlist') {
        if ($exitCode -ne 0 -or $detail.status -ne 'PASS' -or $text -notmatch 'PDS_ADS_GATE_PASS') {
            throw "Positive gate fixture failed; inspect $work"
        }
    } elseif ($exitCode -eq 0 -or $detail.status -ne 'FAIL' -or $detail.error -notmatch 'Frontend mismatch' -or
        $text -match 'PDS_ADS_GATE_PASS') { throw "Audit failure was not propagated to the caller; inspect $work" }
    $results += [ordered]@{
        case = $case; status = 'PASS'; expected = $(if ($case -eq 'actual_netlist') { 'ACCEPT' } else { 'REJECT' })
        exit_code = $exitCode; success_marker = [bool]($text -match 'PDS_ADS_GATE_PASS')
        input_sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        result_sha256 = (Get-FileHash -LiteralPath $report -Algorithm SHA256).Hash.ToLowerInvariant()
        diagnostic = $detail.error
    }
}
if ((Get-FileHash -LiteralPath $Netlist -Algorithm SHA256).Hash.ToLowerInvariant() -ne $originalHash) {
    throw 'The supplied real netlist changed during the fixtures'
}
$scripts = [ordered]@{}
foreach ($name in @('newpc.ps1', 'prepare_pds_project.ps1', 'pds_control_audit.ps1', 'audit_pds_controls.py',
    'bounded_process.cs', 'test_pds_synthesis_gate.ps1', 'test_pds_controls.py')) {
    $scripts[$name] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result = [ordered]@{
    schema = 1; status = 'PASS'; completed_utc = [DateTime]::UtcNow.ToString('o')
    scope = 'Actual bare ADS netlist and synthetic branch0 fault through the shared PdsSynthesis gate; PDS was not rerun'
    netlist_sha256 = $originalHash; scripts = $scripts; cases = $results
    reproduce = 'powershell -NoProfile -File scripts/test_pds_synthesis_gate.ps1 -Netlist <actual-bare-ADS.vm> -PythonPath <python.exe> -OutputPath <result.json>'
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path $OutputPath -Parent) -Force | Out-Null
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output "PDS_SYNTHESIS_GATE_FIXTURES_PASS cases=$($results.Count) result=$OutputPath"
