param([Parameter(Mandatory=$true)][string]$OutputRoot,
      [string]$SynthesisRoot='G:/pfb60s1',
      [string]$GatePath='build/batch60-gates-02.json',
      [string]$PdsShell='G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe',
      [string]$PythonPath='G:/py/ana/python.exe',
      [int]$TimeoutSeconds=14400)
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$receipt=Get-Content -LiteralPath (Join-Path $SynthesisRoot 'resource-evidence/result.json') -Raw|ConvertFrom-Json
if($receipt.status -cne 'SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'){throw 'Native synthesis preflight incomplete'}
$clock=Get-Content -LiteralPath (Join-Path $sourceRoot 'config/clocks.json') -Raw|ConvertFrom-Json
if($clock.cpu_hz -ne 60000000 -or $clock.sys_hz -ne 49500000){throw 'Exact CPU60/SYS49.5 required'}
$gates=Get-Content -LiteralPath (Join-Path $sourceRoot $GatePath) -Raw|ConvertFrom-Json
if($gates.status -cne 'BATCH60_CORRECTNESS_RESOURCE_GATES_PASS_NOT_STA_OR_BOARD'){throw 'Batch correctness/resource gates incomplete'}
foreach($field in $gates.files.PSObject.Properties){
 $path=Join-Path $sourceRoot $field.Name
 if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $field.Value){throw "Gate input/evidence changed: $($field.Name)"}
}
& (Join-Path $PSScriptRoot 'stage_cpu_timing_candidate.ps1') -OutputRoot $OutputRoot -SourceRoot $sourceRoot -Divisor 36 -CpuClockSource dedicated1080frac -DtcPath '/usr/bin/dtc'
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot);$pds=Join-Path $OutputRoot 'pds'
$record=[ordered]@{schema=1;kind='pikafish-batch-cpu60-fresh-standard-build';status='BUILDING';owner_pid=$PID;started_utc=[DateTime]::UtcNow.ToString('o');source_root=$sourceRoot;source_commit=(& git -C $sourceRoot rev-parse HEAD);native_root=$OutputRoot;reference_synthesis_root=$SynthesisRoot;gates_sha256=(Get-FileHash -LiteralPath (Join-Path $sourceRoot $GatePath) -Algorithm SHA256).Hash.ToLowerInvariant();pnr_complete=$false;board=$false}
$launchPath=Join-Path $OutputRoot 'physical-launch.json'
function Save-Record{[IO.File]::WriteAllText($launchPath,($record|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))}
Save-Record
try{
 & (Join-Path $OutputRoot 'scripts/build_fpga.ps1') -UseExistingFirmware -PdsShell $PdsShell -PythonPath $PythonPath -PdsTimeoutSeconds $TimeoutSeconds -CampaignLog (Join-Path $OutputRoot 'pnr-history.json') -AttemptPurpose same_frequency
 $record.status='ROUTED_FULL_STA_PASS_NOT_BOARD'
}catch{$record.status='FAILED';$record.error=$_.Exception.Message}
finally{
 $record.updated_utc=[DateTime]::UtcNow.ToString('o')
 $snapshotPath=Join-Path $pds 'build_snapshot.json'
 if(Test-Path -LiteralPath $snapshotPath){
  $snapshot=Get-Content -LiteralPath $snapshotPath -Raw|ConvertFrom-Json
  $record.run_id=$snapshot.run_id;$record.snapshot_sha256=(Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $record.pnr_complete=(Test-Path -LiteralPath (Join-Path $pds 'report_timing/soc_top.rtr')) -and (Test-Path -LiteralPath (Join-Path $pds 'place_route/soc_top_pnr.netlist'))
  $record.reports=[ordered]@{}
  foreach($name in @('synthesize/soc_top.snr','synthesize/soc_top_syn.vm','synthesize/soc_top_syn.adf','place_route/soc_top.prr','place_route/soc_top_pnr.adf','place_route/soc_top_pnr.netlist','report_timing/soc_top.rtr','report_timing/rtr.db','generate_bitstream/soc_top.sbit','impl.tcl','flow.log')){
   $path=Join-Path $pds $name
   if(Test-Path -LiteralPath $path){$record.reports[$name]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
  }
  if($record.pnr_complete -and $record.status -eq 'FAILED' -and [IO.File]::ReadAllText((Join-Path $pds 'report_timing/soc_top.rtr')) -notmatch 'Design Summary : All Constraints Met\.'){$record.status='ROUTED_STA_FAILED_NOT_BOARD'}
  Save-Record
  Copy-Item -LiteralPath $launchPath -Destination (Join-Path $pds "input-snapshots/$($snapshot.run_id)/physical-result.json")
 }else{Save-Record}
}
Write-Output "BATCH60_PHYSICAL_RESULT status=$($record.status) path=$launchPath"
if($record.status -cne 'ROUTED_FULL_STA_PASS_NOT_BOARD'){exit 2}
