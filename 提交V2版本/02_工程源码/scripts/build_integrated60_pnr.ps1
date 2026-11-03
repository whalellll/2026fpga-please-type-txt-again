param([Parameter(Mandatory=$true)][string]$OutputRoot,
      [string]$PdsShell='G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe',
      [string]$PythonPath='G:/py/ana/python.exe',
      [switch]$NativeLineFix,
      [int]$TimeoutSeconds=14400)
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$required=@('integrated-full-regression-02','integrated-picture-interface-05','integrated-vision-driver-01','integrated-voice-model-02','integrated-voice-mmio-01','integrated-vision-soc-01','integrated-vision-nnue-01','integrated-pikafish-runtime-02','integrated-voice-rv32-01','integrated-boot60-01')
if($NativeLineFix){
 $required=@($required | Where-Object {$_ -notin @('integrated-full-regression-02','integrated-vision-soc-01','integrated-vision-nnue-01')})
 $required+=@('integrated-full-regression-03','integrated-vision-line-pass-01','integrated-real-ddr-pass-01','integrated-vision-nnue-02')
}
$checks=[ordered]@{}
foreach($name in $required){
 $path=Join-Path $sourceRoot "build/$name/result.json"
 $r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json
 if($r.status -notmatch 'PASS|BOOT_CANDIDATE_BUILT_NOT_BOARD_TESTED'){throw "Required offline gate failed: $name $($r.status)"}
 if($NativeLineFix -and $name -in @('integrated-full-regression-03','integrated-vision-line-pass-01','integrated-real-ddr-pass-01','integrated-vision-nnue-02')){
  foreach($entry in $r.source_sha256.PSObject.Properties){
   $p=if([IO.Path]::IsPathRooted($entry.Name)){$entry.Name}else{Join-Path $sourceRoot $entry.Name}
   if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw "Regression input changed: $name $($entry.Name)"}
  }
 }
 $checks[$name]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$kernel=Join-Path $sourceRoot 'build/integrated-kernel-02/build.json'
if((Get-Content -LiteralPath $kernel -Raw|ConvertFrom-Json).status -cne 'VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD'){throw 'Current kernel not built'}
$checks.kernel=(Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant()
$resource=Join-Path $sourceRoot 'build/integrated-resources-01.json'
if($NativeLineFix){$resource=Join-Path $sourceRoot 'build/integrated-resources-linefix-01.json'}
if((Get-Content -LiteralPath $resource -Raw|ConvertFrom-Json).status -cne 'INTEGRATED60_NATIVE_RESOURCES_AND_RETAINED_ENGINES_PASS_NOT_STA_OR_BOARD'){throw 'Resource gate missing'}
$checks.resources=(Get-FileHash -LiteralPath $resource -Algorithm SHA256).Hash.ToLowerInvariant()
foreach($name in @('integrated-composed-audit-01','integrated-pma-faults-01','integrated-audit-selection-02','integrated-vision-profile-01','integrated-p2-cdc','integrated-p2-sd-owner','integrated-p2-sd-storage','integrated-p2-vision-retention')){
 $path=Join-Path $sourceRoot "build/$name.json";$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json
 if($r.status -notmatch 'PASS|PROVED'){throw "Combined native preflight validation missing: $name"}
 $checks[$name]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
& (Join-Path $PSScriptRoot 'stage_cpu_timing_candidate.ps1') -OutputRoot $OutputRoot -SourceRoot $sourceRoot -Divisor 36 -CpuClockSource dedicated1080frac -DtcPath '/usr/bin/dtc'
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot);$pds=Join-Path $OutputRoot 'pds'
$record=[ordered]@{schema=1;kind='integrated60-fresh-standard-build';status='BUILDING';owner_powershell_pid=$PID;started_utc=[DateTime]::UtcNow.ToString('o');source_root=$sourceRoot;source_commit=(& git -C $sourceRoot rev-parse HEAD);native_root=$OutputRoot;checks=$checks;cpu_hz=60000000;sys_hz=49500000;display='1080p30';vision_weights=$(if($NativeLineFix){'ORIGINAL_MODELS_RECOVERED_SD04'}else{'DEFERRED_BY_USER_INTERFACE_ONLY'});native_line_fix=[bool]$NativeLineFix;pnr_started=$false;pnr_complete=$false;board=$false;push=$false;delivery=$false}
$launchPath=Join-Path $OutputRoot 'physical-launch.json'
function Save-Record { [IO.File]::WriteAllText($launchPath,($record|ConvertTo-Json -Depth 14)+"`n",[Text.UTF8Encoding]::new($false)) }
Save-Record
try {
 & (Join-Path $OutputRoot 'scripts/build_fpga.ps1') -UseExistingFirmware -PdsShell $PdsShell -PythonPath $PythonPath -PdsTimeoutSeconds $TimeoutSeconds -CampaignLog (Join-Path $OutputRoot 'pnr-history.json') -AttemptPurpose final
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
Write-Output "INTEGRATED60_PHYSICAL_RESULT status=$($record.status) path=$launchPath"
if($record.status -cne 'ROUTED_FULL_STA_PASS_NOT_BOARD'){exit 2}
