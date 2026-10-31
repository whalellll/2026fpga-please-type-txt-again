param([string]$PortName='COM5',[Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$LogPath,[string]$RestoreMmodeCrc='')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$contract=Get-Content -LiteralPath (Join-Path $out 'sd_contract.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$prefix=[string]$contract.deployment.prefix
if($prefix -notmatch '^[A-Z][A-Z0-9]{1,2}$'){throw 'Invalid candidate FAT prefix'}
$backupName=$prefix+'XOLD.BIN'
$log=[IO.Path]::GetFullPath($LogPath)
if((Test-Path $log) -or (Test-Path ($log+'.loader.log'))){throw 'Use fresh logs'}
$image=Join-Path $out 'install-sd-console.bin'
& (Join-Path $PSScriptRoot 'serial_boot_v2_1_sd.ps1') -PortName $PortName -ImagePath $image `
 -LoadAddress 0x01800000 -LogPath ($log+'.loader.log') -SuccessMarker SD_CONSOLE_READY `
 -FailureMarkers @('SD_CONSOLE_FAIL','SD_CONSOLE_REPAIR_REQUIRED','Kernel panic') -TimeoutSeconds 40
if($LASTEXITCODE){throw 'SD console installer failed to start'}
$port=New-Object IO.Ports.SerialPort($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.ReadTimeout=200;$port.WriteTimeout=10000;$port.DtrEnable=$false;$port.RtsEnable=$false
$transcript=New-Object Text.StringBuilder
function Wait-Board([string]$needle,[int]$seconds){
 $part=New-Object Text.StringBuilder;$end=[DateTime]::UtcNow.AddSeconds($seconds)
 while([DateTime]::UtcNow -lt $end){
  $text=$port.ReadExisting()
  if($text){[void]$part.Append($text);[void]$transcript.Append($text)
   if($part.ToString() -match 'SD_CONSOLE_FAIL|REPAIR_REQUIRED|Kernel panic|SD payload CRC mismatch'){throw 'SD console update/boot failed; inspect saved log and verified backup'}
   if($part.ToString().Contains($needle)){return}
  }else{Start-Sleep -Milliseconds 20}
 }
 throw "Timeout $needle"
}
$passed=$false
try{
 $port.Open();$port.Write("`r");Wait-Board 'sdentry> ' 10
 if($RestoreMmodeCrc){
  if($RestoreMmodeCrc -notmatch '^0x[0-9a-fA-F]{8}$'){throw 'Invalid original M-mode CRC'}
  $port.Write("restore-mmode $RestoreMmodeCrc`r");Wait-Board 'SD_CONSOLE_RESTORE_MMODE_PASS' 60
  Write-Host 'ORIGINAL_MMODE_RESTORED_AND_CRC_VERIFIED'
 }
 $port.Write("install`r");Wait-Board 'SD_CONSOLE_INSTALL_PASS' 120
 Write-Host ('PICTURE_SD_CONSOLE_INSTALL_PASS backup='+$backupName)
 $port.Write("console`r");Wait-Board 'soc> ' 20
 $port.Write("xqboot`r");Wait-Board 'XQ LINUX PIKAFISH READY' 420
 Write-Host 'PICTURE_ROM_XQBOOT_LINUX_PASS uart_payloads_after_console=0'
 $passed=$true
}finally{
 if($port.IsOpen){$port.Close()};$port.Dispose()
 [IO.File]::WriteAllText($log,$transcript.ToString(),(New-Object Text.UTF8Encoding($false)))
}
if($passed){
 $original=[regex]::Match($transcript.ToString(),'SD_CONSOLE_ORIGINAL bytes=(\d+) crc=(0x[0-9a-f]+)')
 $patched=[regex]::Match($transcript.ToString(),'SD_CONSOLE_IMAGE_READBACK_PASS name=xiangqi.bin bytes=(\d+) crc=(0x[0-9a-f]+)')
 if(!$original.Success -or !$patched.Success){throw 'Missing complete backup/readback receipt'}
 $result=@{schema_version=1;scope='Manual frozen-ROM xqboot chain, NOT BoardRelease';status='PASS';
  original_name='xiangqi.bin';original_bytes=[int]$original.Groups[1].Value;original_crc32=$original.Groups[2].Value;
  backup_name=$backupName;patched_crc32=$patched.Groups[2].Value;command='xqboot';mmode_restored_crc32=$RestoreMmodeCrc;
  uart_payloads_after_console=0;flash_written=$false;default_stops_at_console=$true;
  sd_loader_sha256=(Get-FileHash (Join-Path $out 'loader-picture-candidate.bin') -Algorithm SHA256).Hash.ToLowerInvariant();
  installer_sha256=(Get-FileHash $image -Algorithm SHA256).Hash.ToLowerInvariant();
  uart_log_sha256=(Get-FileHash $log -Algorithm SHA256).Hash.ToLowerInvariant()}
 [IO.File]::WriteAllText(($log+'.json'),($result|ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
}
