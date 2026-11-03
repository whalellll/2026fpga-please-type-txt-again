param([Parameter(Mandatory=$true)][string]$CandidateDirectory,
      [Parameter(Mandatory=$true)][string]$LogPath,
      [string]$PortName='COM5',[switch]$Install,[switch]$Boot,[switch]$PreflightOnly)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$candidate=[IO.Path]::GetFullPath($CandidateDirectory)
$log=[IO.Path]::GetFullPath($LogPath)
if((Test-Path -LiteralPath $log)-or(Test-Path -LiteralPath ($log+'.load.log'))){throw 'Choose fresh SD migration logs'}
$plan=Get-Content -LiteralPath (Join-Path $candidate 'namespace-install-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($plan.expected_cid -cne 'f40101c3803919885333324703534453' -or $plan.media_sectors -ne 62333952 -or $plan.partition_lba -ne 32){throw 'Unexpected selected card contract'}
foreach($entry in @($plan.original_entry,$plan.embedded.loader,$plan.embedded.menu,$plan.embedded.config)){
 if((Get-Item -LiteralPath $entry.path).Length -ne $entry.bytes -or
    (Get-FileHash -LiteralPath $entry.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256){throw 'SD migration input identity changed'}
}
$image=Join-Path $candidate 'xq-sd-namespace-install.bin'
if(-not(Test-Path -LiteralPath $image)){throw 'Build installer first'}
if($PreflightOnly){Write-Output 'SD_NAMESPACE_PREFLIGHT_PASS no_hardware_access=1';return}
if($Boot -and -not $Install){throw 'Boot requires completed Install'}
& (Join-Path $repo 'scripts/serial_boot_v2_1_sd.ps1') -PortName $PortName -ImagePath $image -LoadAddress 0x01800000 `
 -LogPath ($log+'.load.log') -SuccessMarker NS_INSTALL_READY -FailureMarkers @('NS_INSTALL_FAIL','NS_REPAIR_REQUIRED') -TimeoutSeconds 40
$load=Get-Content -LiteralPath ($log+'.load.log') -Raw
$cid=[regex]::Match($load,'NS_CID=([a-f0-9]{32}) sectors=62333952 partition_lba=32')
if(-not $cid.Success -or $cid.Groups[1].Value -cne $plan.expected_cid){throw 'Fresh board CID disagrees with selected card; no write issued'}
$serial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=200;$serial.WriteTimeout=1000
$transcript=[Text.StringBuilder]::new();$passed=$false;$script:pending=''
function Send-Paced([string]$Text){foreach($c in $Text.ToCharArray()){$serial.Write([string]$c);Start-Sleep -Milliseconds 3}}
function Wait-Board([string]$Needle,[int]$Seconds){
 $deadline=[DateTime]::UtcNow.AddSeconds($Seconds);$part=[Text.StringBuilder]::new()
 [void]$part.Append($script:pending);$script:pending=''
 while([DateTime]::UtcNow -lt $deadline){
  $text=$part.ToString()
  if($text -match 'NS_INSTALL_FAIL|NS_REPAIR_REQUIRED|XQ_BOOT_MENU_FAIL|XQ_BOOT_MENU_REJECT|SD payload invalid|SD payload CRC mismatch|SD load failed|SD_LOADER_FAIL|Kernel panic|XQ_MODEL_START_FAILED'){
   throw 'SD migration/boot failed; preserve transcript and verified backups; no automatic write retry'
  }
  $at=$text.IndexOf($Needle,[StringComparison]::Ordinal)
  if($at -ge 0){$script:pending=$text.Substring($at+$Needle.Length);return}
  $chunk=$serial.ReadExisting()
  if($chunk){
   [void]$part.Append($chunk);[void]$transcript.Append($chunk);Write-Host -NoNewline $chunk
  }
  Start-Sleep -Milliseconds 100
 }
 throw ('Bounded SD operation timed out waiting for '+$Needle)
}
try {
 $serial.Open();Send-Paced "`r";Wait-Board 'nsinstall> ' 10
 Send-Paced "inspect`r";Wait-Board 'NS_INSPECT_PASS no_writes=1' 240;Wait-Board 'nsinstall> ' 10
 if($Install){
  Send-Paced ('install '+$cid.Groups[1].Value+"`r")
  Wait-Board 'NS_INSTALL_PASS' 900;Wait-Board 'nsinstall> ' 10
  $text=$transcript.ToString()
  if([regex]::Matches($text,'NS_READBACK_CRC_PASS name=').Count -ne 10 -or
     [regex]::Matches($text,'NS_PAIR_COMMITTED ').Count -ne 5 -or
     $text -notmatch ('NS_SHARED_MENU_ENTRY_PASS bytes=20468 crc=0x'+$plan.new_entry.crc32)){
   throw 'Incomplete SD commit/readback proof'
  }
  Send-Paced "console`r";Wait-Board 'soc> ' 20
  if($Boot){
   Send-Paced "xqboot`r";Wait-Board 'bootmenu> ' 30;Send-Paced "1`r"
   Wait-Board 'XQ LINUX PIKAFISH READY' 420
   $text=$transcript.ToString()
   foreach($entry in $plan.source_files_and_private_copies){
    $pattern='Loading '+[regex]::Escape($entry.name)+' bytes='+$entry.bytes+'[\s\S]*?CRC32=0x'+$entry.crc32
    if($text -notmatch $pattern){throw ('Private boot payload proof absent: '+$entry.name)}
   }
   if($text -notmatch 'rv32-driver-quantized-mac.*camera=background'){throw 'Native background runtime proof absent'}
   Write-Output 'SD_RESIDENT_MENU_BOOT_PASS recurring_uart_file_upload=0'
  }
  Write-Output 'SD_NAMESPACE_MIGRATION_PASS files=10 backup=PN00BOOT.BIN flash_written=0'
 }else{Write-Output 'SD_NAMESPACE_INSPECT_ONLY_PASS writes=0'}
 $passed=$true
}finally{
 if($serial.IsOpen){$serial.Close()};$serial.Dispose()
 [IO.File]::WriteAllText($log,$transcript.ToString(),[Text.UTF8Encoding]::new($false))
 $receipt=[ordered]@{schema_version=1;status=if($passed){'PASS'}else{'FAILED'};sd_write_authorized=[bool]$Install;
  boot_from_sd_menu=[bool]($passed -and $Install -and $Boot);recurring_uart_file_upload=$false;
  cid=$cid.Groups[1].Value;flash_written=$false;
  install_plan_sha256=(Get-FileHash -LiteralPath (Join-Path $candidate 'namespace-install-plan.json') -Algorithm SHA256).Hash.ToLowerInvariant();
  installer_sha256=(Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant();
  uart_log_sha256=(Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()}
 [IO.File]::WriteAllText(($log+'.json'),($receipt|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
}
