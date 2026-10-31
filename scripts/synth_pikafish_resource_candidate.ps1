param([Parameter(Mandatory=$true)][string]$OutputRoot,
      [string]$PdsShell='G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe',
      [int]$TimeoutSeconds=1800)
# Resource experiment only: no post-synthesis project, PnR, bitstream or board.
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'stage_cpu_timing_candidate.ps1') -OutputRoot $OutputRoot -SourceRoot $sourceRoot -Divisor 9 -DtcPath '/usr/bin/dtc'
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
$pds=Join-Path $OutputRoot 'pds'
foreach($asset in @('font8x16.hex','header_bitmap.hex','header_logo_rgb332.hex')){
 Copy-Item -LiteralPath (Join-Path $OutputRoot "rtl/video/$asset") -Destination (Join-Path $pds $asset)
}
& (Join-Path $OutputRoot 'scripts/prepare_pds_project.ps1') -ValidateOnly
. (Join-Path $OutputRoot 'scripts/build_snapshot.ps1')
$frozen=Get-FpgaHashMap $OutputRoot (Get-FpgaInputPaths $OutputRoot)
$evidence=Join-Path $OutputRoot 'resource-evidence'
New-Item -ItemType Directory -Path $evidence | Out-Null
$record=[ordered]@{schema=1;kind='pikafish-dedicated-synthesis-resource-experiment';started_utc=[DateTime]::UtcNow.ToString('o');source_root=$sourceRoot;native_root=$OutputRoot;inputs=$frozen;status='RUNNING';pnr=$false;board=$false;production_driver_compatible=$false}
$recordPath=Join-Path $evidence 'result.json'
function Save-Record { [IO.File]::WriteAllText($recordPath,($record | ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false)) }
Save-Record
if(!('CpuSimulation.BoundedProcess' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')}
try {
 foreach($job in @(@('parse','-parsetcl soc.tcl soc_pre_synth.pds -model 3',120),@('synth','-project soc_pre_synth.pds -run synthesize',$TimeoutSeconds))){
  $prefix=Join-Path $evidence $job[0]
  Write-Output "RESOURCE_EXPERIMENT_START $($job[0]) $([DateTime]::UtcNow.ToString('o'))"
  $rc=[CpuSimulation.BoundedProcess]::Run($PdsShell,$job[1],$pds,"$prefix.stdout.log","$prefix.stderr.log",[int]$job[2])
  if($rc -ne 0){throw "PDS $($job[0]) failed: $rc"}
  if(Select-String -LiteralPath "$prefix.stdout.log","$prefix.stderr.log" -Pattern '^E:|Program Error Out\.' -Quiet){throw "PDS $($job[0]) reported errors despite exit zero"}
 }
 Assert-FpgaMap $frozen (Get-FpgaHashMap $OutputRoot @($frozen.Keys)) 'Synthesis frozen inputs'
 $record.reports=[ordered]@{}
 foreach($path in @('synthesize/soc_top.snr','synthesize/soc_top_syn.vm','synthesize/soc_top_syn.adf','impl.tcl','flow.log')){
  $file=Get-Item -LiteralPath (Join-Path $pds $path)
  if($file.LastWriteTimeUtc -lt [DateTime]::Parse($record.started_utc).ToUniversalTime()){throw "Stale output: $path"}
  $record.reports[$path]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
 }
 $reportText=[IO.File]::ReadAllText((Join-Path $pds 'synthesize/soc_top.snr'))
 if($reportText -notmatch 'Number of Slice Registers|Number of Registers|Design Statistics|Resource Usage|Resource Information|Total LUTs|LUT') {throw 'Missing resource report'}
 $record.status='SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
} catch { $record.status='FAILED';$record.error=$_.Exception.Message;throw }
finally {$record.completed_utc=[DateTime]::UtcNow.ToString('o');Save-Record}
Write-Output "RESOURCE_EXPERIMENT_COMPLETE $recordPath"
