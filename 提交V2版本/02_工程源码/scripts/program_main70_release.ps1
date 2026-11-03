[CmdletBinding()]
param([switch]$Program,[switch]$DryRun,[string]$PdsRoot='G:/fpga/PDS_2022.2-SP6.4',
      [string]$PythonPath='G:/py/ana/python.exe',[int]$JtagServerPort=65421,
      [string]$LogPath,[string]$EvidencePath)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(!(Test-Path -LiteralPath (Join-Path $root 'MAIN70_DELIVERY.json'))){throw 'Use the sealed Main70 delivery package; source candidates retain their own gate.'}
& (Join-Path $PSScriptRoot 'audit_main70_delivery.ps1') -Root $root -CheckHashes
& $PythonPath -B (Join-Path $PSScriptRoot 'verify_main70_delivery.py') --root $root
if($LASTEXITCODE -ne 0){throw 'Main70 sealed content or implementation verification failed'}
$trial=Join-Path $root 'docs/validation/main70-release-20261027/native'
$native=Join-Path $trial 'result.json'
if(!(Test-Path -LiteralPath $native)){throw 'Packaged exact native result is missing'}
# The existing programmer retains exact Tcl/ID/assignment/DONE and pre/post
# native checks. This wrapper adds the full package/project acceptance gate.
$programArgs=@{Program=$Program;DryRun=$DryRun;PdsRoot=$PdsRoot;
    AuditProfile='Main70Candidate';TrialDirectory=$trial;JtagServerPort=$JtagServerPort}
if($LogPath){$programArgs.LogPath=$LogPath}
if($EvidencePath){$programArgs.EvidencePath=$EvidencePath}
& (Join-Path $PSScriptRoot 'program_cram.ps1') @programArgs
if($LASTEXITCODE -ne 0){throw 'Main70 CRAM programmer failed'}
