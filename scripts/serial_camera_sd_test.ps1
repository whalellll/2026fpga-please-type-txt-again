param([string]$PortName='COM5',[ValidateRange(1,20)][int]$CaptureCount=2,
 [ValidateRange(10,120)][int]$SaveTimeoutSeconds=75,[switch]$TestEsc,
 [ValidateRange(0,5000)][int]$PreviewSettleMilliseconds=1000,
 [switch]$AllowEmptyBootCard,[string]$LogPath)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(!$LogPath){$LogPath=Join-Path $root 'artifacts/board_camera_sd.log'}
$capture=[Text.StringBuilder]::new()
$port=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.ReadTimeout=100;$port.WriteTimeout=1000;$port.DtrEnable=$false;$port.RtsEnable=$false
function Read-Until([string]$Marker,[int]$Seconds){
 $part=[Text.StringBuilder]::new();$deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
 while([DateTime]::UtcNow -lt $deadline){
  try{$s=$port.ReadExisting()}catch [TimeoutException]{$s=''}
  if($s){[void]$part.Append($s);[void]$capture.Append($s);Write-Host -NoNewline $s
   if($part.ToString().Contains($Marker)){return $part.ToString()}}
  Start-Sleep -Milliseconds 20
 }
 throw "UART timeout waiting for $Marker"
}
function Send-Command([string]$Text){
 foreach($ch in ($Text+"`r").ToCharArray()){$port.Write([string]$ch);Start-Sleep -Milliseconds 5}
}
function Check-BootFiles {
 Send-Command 'sdverify';$s=Read-Until 'soc> ' 90
 if(!$s.Contains('SD_VERIFY_READ_ONLY_PASS files=4')){
  if(!$AllowEmptyBootCard){throw 'Read-only boot-file verification failed'}
  $cid=[regex]::Match($s,'SD verify CID=([^\r\n]+)').Groups[1].Value
  if(!$cid -or !$s.Contains('fw_jump.bin (file not found)')){throw 'Card is not an empty Linux boot card'}
  Send-Command 'sdinfo';$info=Read-Until 'soc> ' 20
  foreach($name in @('fw_jump.bin','Image','rootfs.cpio','soc.dtb')){
   if(!$info.Contains($name+': file not found')){throw 'Partial Linux boot card: prepare/verify all four files first'}
  }
  $geometry=[regex]::Match($info,'Filesystem: FAT32[^\r\n]+').Value
  if(!$geometry){throw 'Expected FAT32 card'}
  return 'EMPTY_BOOT_FILES;'+$cid+';'+$geometry
 }
 $matches=[regex]::Matches($s,'SD_VERIFY ([^\r\n]+) bytes=([0-9]+) CRC32=(0x[0-9a-fA-F]+)')
 if($matches.Count -ne 4){throw 'Expected four file CRCs'}
 $cid=[regex]::Match($s,'SD verify CID=([^\r\n]+)').Groups[1].Value
 if(!$cid){throw 'Missing card identity'}
 return $cid+';'+(($matches|ForEach-Object{$_.Value}) -join ';')
}
try {
 $port.Open();$port.DiscardInBuffer();$port.Write([string][char]27);Send-Command '';[void](Read-Until 'soc> ' 15)
 $before=Check-BootFiles
 Send-Command 'debug camera_sd';[void](Read-Until 'Destination: SD /CAMERA' 15)
 Start-Sleep -Milliseconds $PreviewSettleMilliseconds
 for($shot=0;$shot -lt $CaptureCount;$shot++){
  $saveWatch=[Diagnostics.Stopwatch]::StartNew()
  $port.Write('  ');$s=Read-Until 'Photo saved and verified on SD.' $SaveTimeoutSeconds
  $saveWatch.Stop()
  if(!$s.Contains('Camera busy;') -or $s -notmatch 'SD saved: /CAMERA/(IMG[0-9]{5}\.PNG)'){throw 'Missing save/busy confirmation'}
  Write-Host "`nUART SD capture verified: $($Matches[1])"
  $timing="UART_SD_SAVE_MS file=$($Matches[1]) elapsed_ms=$($saveWatch.ElapsedMilliseconds)"
  Write-Output $timing;[void]$capture.Append($timing+"`n")
 }
 if($TestEsc){
  $port.Write(' ');[void](Read-Until 'SD writing PNG;' 30);Start-Sleep -Milliseconds 100
  $port.Write([string][char]27);$s=Read-Until 'soc> ' 15
  if(!$s.Contains('SD photo failed: CANCELLED') -or !$s.Contains('Camera stopped; bootloader terminal restored.')){throw 'Esc cleanup/safe stop failed'}
  Send-Command 'debug camera_sd';[void](Read-Until 'Destination: SD /CAMERA' 15)
  Start-Sleep -Milliseconds $PreviewSettleMilliseconds
  $port.Write(' ');[void](Read-Until 'Photo saved and verified on SD.' $SaveTimeoutSeconds)
 }
 $port.Write([string][char]27);[void](Read-Until 'soc> ' 15)
 $after=Check-BootFiles
 if($before -cne $after){throw 'Card identity / existing Linux boot-file CRC changed'}
 if($before.StartsWith('EMPTY_BOOT_FILES;')){
  Write-Output 'BOARD_CAMERA_SD_UART_BUSY_ESC_RETRY_EMPTY_CARD_PASS'
  Write-Warning 'Linux boot files were absent; this run does not verify protection of existing boot files.'
 }else{Write-Output 'BOARD_CAMERA_SD_UART_BUSY_ESC_RETRY_BOOT_FILES_PASS'}
} finally {
 if($port.IsOpen){
  try{$port.Write([string][char]27);Send-Command '';[void](Read-Until 'soc> ' 15)}
  catch{Write-Warning 'Terminal restoration was not confirmed; press Esc/check the board.'}
  $port.Close()
 };$port.Dispose()
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($LogPath),$capture.ToString(),[Text.UTF8Encoding]::new($false))
}
