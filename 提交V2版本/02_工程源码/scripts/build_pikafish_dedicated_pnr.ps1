param([Parameter(Mandatory=$true)][string]$OutputRoot,
      [string]$SynthesisRoot='G:/pfdsyn2',
      [string]$PdsShell='G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe',
      [string]$PythonPath='G:/py/ana/python.exe',
      [int]$TimeoutSeconds=14400)
# Fresh native synthesis and physical implementation, using the standard flow.
# Same RTL/clock/constraints as the resource experiment; no inherited freshness.
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$receipt=Get-Content -LiteralPath (Join-Path $SynthesisRoot 'resource-evidence/result.json') -Raw|ConvertFrom-Json
if($receipt.status -cne 'SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'){throw 'Reference synthesis not completed'}
$toolChanges=@('scripts/audit_cpu_dedicated_pll_ads.py','scripts/build_cpu_ads_gate.ps1','scripts/build_snapshot.ps1','scripts/audit_cpu_ads.py')
foreach($field in $receipt.inputs.PSObject.Properties){
 $h=(Get-FileHash -LiteralPath (Join-Path $sourceRoot $field.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
 if($h -cne $field.Value -and $field.Name -notin $toolChanges){throw "Reference hardware input changed: $($field.Name)"}
}
& (Join-Path $PSScriptRoot 'stage_cpu_timing_candidate.ps1') -OutputRoot $OutputRoot -SourceRoot $sourceRoot -Divisor 9 -DtcPath '/usr/bin/dtc'
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot);$pds=Join-Path $OutputRoot 'pds'
$record=[ordered]@{schema=1;kind='pikafish-dedicated-fresh-standard-build';status='BUILDING';owner_powershell_pid=$PID;started_utc=[DateTime]::UtcNow.ToString('o');source_root=$sourceRoot;source_commit=(& git -C $sourceRoot rev-parse HEAD);native_root=$OutputRoot;reference_synthesis_root=$SynthesisRoot;reference_synthesis=$receipt.reports;pnr_started=$false;pnr_complete=$false;board=$false;production_driver_compatible=$false;tool_input_changes=$toolChanges}
$launchPath=Join-Path $OutputRoot 'physical-launch.json'
function Save-Record { [IO.File]::WriteAllText($launchPath,($record|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false)) }
Save-Record
try {
 & (Join-Path $OutputRoot 'scripts/build_fpga.ps1') -UseExistingFirmware -PdsShell $PdsShell -PythonPath $PythonPath -PdsTimeoutSeconds $TimeoutSeconds -CampaignLog (Join-Path $OutputRoot 'pnr-history.json') -AttemptPurpose same_frequency
 $record.status='ROUTED_FULL_STA_PASS_NOT_BOARD'
} catch {$record.status='FAILED';$record.error=$_.Exception.Message}
finally {
 $record.updated_utc=[DateTime]::UtcNow.ToString('o')
 $snapshotPath=Join-Path $pds 'build_snapshot.json'
 if(Test-Path -LiteralPath $snapshotPath){
  $snapshot=Get-Content -LiteralPath $snapshotPath -Raw|ConvertFrom-Json
  $record.run_id=$snapshot.run_id;$record.snapshot_sha256=(Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $record.pnr_started=Test-Path -LiteralPath (Join-Path $OutputRoot 'pnr-history.json')
  $record.pnr_complete=(Test-Path -LiteralPath (Join-Path $pds 'report_timing/soc_top.rtr')) -and (Test-Path -LiteralPath (Join-Path $pds 'place_route/soc_top_pnr.netlist'))
  $record.reports=[ordered]@{}
  foreach($name in @('synthesize/soc_top.snr','synthesize/soc_top_syn.vm','synthesize/soc_top_syn.adf','place_route/soc_top.prr','place_route/soc_top_pnr.adf','place_route/soc_top_pnr.netlist','place_route/soc_top_prr.prt','report_timing/soc_top.rtr','report_timing/rtr.db','generate_bitstream/soc_top.sbit','device_map/soc_top.dmr','device_map/soc_top.pcf','impl.tcl','flow.log')){
   $path=Join-Path $pds $name
   if(Test-Path -LiteralPath $path){$record.reports[$name]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
  }
  if($record.pnr_complete -and $record.status -eq 'FAILED' -and [IO.File]::ReadAllText((Join-Path $pds 'report_timing/soc_top.rtr')) -notmatch 'Design Summary : All Constraints Met\.'){$record.status='ROUTED_STA_FAILED_NOT_BOARD'}
  Save-Record
  Copy-Item -LiteralPath $launchPath -Destination (Join-Path $pds "input-snapshots/$($snapshot.run_id)/physical-result.json")
 }else{Save-Record}
}
Write-Output "DEDICATED_PHYSICAL_RESULT status=$($record.status) path=$launchPath"
if($record.status -cne 'ROUTED_FULL_STA_PASS_NOT_BOARD'){exit 2}
