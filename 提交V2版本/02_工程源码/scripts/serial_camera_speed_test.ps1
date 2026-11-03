param(
 [string]$PortName='COM5',
 [ValidateSet('Both','SD','UDP')][string]$Mode='Both',
 [ValidateRange(2,10)][int]$CaptureCount=3,
 [ValidateRange(10,120)][int]$SaveTimeoutSeconds=75,
 [ValidateRange(0,5000)][int]$PreviewSettleMilliseconds=1000,
 [string]$LogPath
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(!$LogPath){$LogPath=Join-Path $root 'artifacts/board_camera_speed.log'}
$capture=[Text.StringBuilder]::new()
$port=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.WriteTimeout=1000;$port.DtrEnable=$false;$port.RtsEnable=$false
function Read-Until([string]$Marker,[int]$Seconds){
 $part=[Text.StringBuilder]::new();$deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
 while([DateTime]::UtcNow -lt $deadline){
  $s=$port.ReadExisting()
  if($s){[void]$part.Append($s);[void]$capture.Append($s);Write-Host -NoNewline $s
   if($part.ToString().Contains($Marker)){return $part.ToString()}
   if($Marker.StartsWith('Photo saved') -and $part.ToString().Contains('Photo failed;')){
    throw 'Capture/save failed; check the SD card or start the PC receiver'
   }
   if($Marker.StartsWith('Photo saved') -and
      ($part.ToString().Contains('Camera stopped; bootloader terminal restored.') -or
       $part.ToString().Contains('soc> '))){
    throw 'Capture was cancelled; the camera returned to the terminal'
   }}
  Start-Sleep -Milliseconds 10
 }
 throw "UART timeout waiting for $Marker"
}
function Record([string]$Text){Write-Output $Text;[void]$capture.Append($Text+"`n")}
$results=@{}
try{
 $port.Open();$port.DiscardInBuffer();$port.Write([string][char]27);$port.Write("`r")
 [void](Read-Until 'soc> ' 15)
 $port.Write("info`r");[void](Read-Until 'soc> ' 15)
 $modes=if($Mode -eq 'Both'){@('SD','UDP')}else{@($Mode)}
 foreach($destination in $modes){
  $command=if($destination -eq 'SD'){'debug camera_sd'}else{'debug camera'}
  $success=if($destination -eq 'SD'){'Photo saved and verified on SD.'}else{'Photo saved by PC.'}
  $port.Write($command+"`r")
  [void](Read-Until 'Camera is live on HDMI.' 20)
  Start-Sleep -Milliseconds $PreviewSettleMilliseconds
  $times=[Collections.Generic.List[long]]::new()
  for($shot=0;$shot -lt $CaptureCount;$shot++){
   $watch=[Diagnostics.Stopwatch]::StartNew();$port.Write(' ')
   $output=Read-Until $success $SaveTimeoutSeconds;$watch.Stop()
   if($output -notmatch 'Saving frame ([0-9]+);'){throw 'Missing complete-frame capture confirmation'}
   $frame=$Matches[1];$times.Add($watch.ElapsedMilliseconds)
   Record "CAMERA_SAVE_MS destination=$destination shot=$shot frame=$frame elapsed_ms=$($watch.ElapsedMilliseconds)"
  }
  $port.Write([string][char]27);$stopped=Read-Until 'soc> ' 15
  if(!$stopped.Contains('Camera stopped; bootloader terminal restored.')){throw 'Camera safe stop was not confirmed'}
  $results[$destination]=@($times)
  $stats=$times|Measure-Object -Average -Minimum -Maximum
  $sorted=@($times|Sort-Object);$middle=[int][Math]::Floor($sorted.Count/2)
  $median=if($sorted.Count%2){$sorted[$middle]}else{($sorted[$middle-1]+$sorted[$middle])/2.0}
  Record "CAMERA_SAVE_SUMMARY destination=$destination samples=$($times.Count) mean_ms=$([Math]::Round($stats.Average,1)) median_ms=$median min_ms=$($stats.Minimum) max_ms=$($stats.Maximum)"
 }
 if($Mode -eq 'Both'){
  $sd=($results['SD']|Measure-Object -Average).Average
  $udp=($results['UDP']|Measure-Object -Average).Average
  if($sd -ge $udp){throw "SD complete-save target not met: SD=$sd ms, UDP=$udp ms"}
  Record "SD_COMPLETE_SAVE_FASTER_THAN_PC_PASS sd_mean_ms=$([Math]::Round($sd,1)) udp_mean_ms=$([Math]::Round($udp,1))"
 }
}finally{
 if($port.IsOpen){
  try{$port.Write([string][char]27);$port.Write("`r");[void](Read-Until 'soc> ' 15)}
  catch{Write-Warning 'Terminal restoration was not confirmed; press Esc/check the board.'}
  $port.Close()
 }
 $port.Dispose()
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($LogPath),$capture.ToString(),[Text.UTF8Encoding]::new($false))
}
