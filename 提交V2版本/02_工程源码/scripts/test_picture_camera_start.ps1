param(
 [string]$PortName='COM5',
 [ValidateRange(1,10)][int]$Attempts=5,
 [Parameter(Mandatory=$true)][string]$EvidencePrefix
)
# Run only at the immutable bootloader's soc> prompt. No Space, SD or Flash.
$ErrorActionPreference='Stop'
foreach($suffix in @('.log','.json')) {
 if(Test-Path -LiteralPath ($EvidencePrefix+$suffix)){throw 'Use fresh camera evidence paths'}
}
$port=New-Object IO.Ports.SerialPort($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.DtrEnable=$false;$port.RtsEnable=$false;$port.WriteTimeout=1000
$transcript=New-Object Text.StringBuilder
$results=New-Object Collections.Generic.List[object]
function Wait-CameraText([string]$pattern,[int]$seconds) {
 $data=New-Object Text.StringBuilder
 $deadline=[DateTime]::UtcNow.AddSeconds($seconds)
 while([DateTime]::UtcNow -lt $deadline) {
  $chunk=$port.ReadExisting()
  if($chunk) {
   [void]$data.Append($chunk);[void]$transcript.Append($chunk)
   if($data.ToString() -match $pattern){return $data.ToString()}
  } else {Start-Sleep -Milliseconds 10}
 }
 throw "Camera console timeout: $pattern"
}
try {
 $port.Open();$port.Write("`r");[void](Wait-CameraText 'soc> ' 3)
 for($attempt=1;$attempt -le $Attempts;$attempt++) {
  $watch=[Diagnostics.Stopwatch]::StartNew()
  $port.Write("debug camera`r")
  $reply=Wait-CameraText 'Camera is live on HDMI\.|soc> ' 15
  $live=$reply.Contains('Camera is live on HDMI.')
  $elapsed=$watch.ElapsedMilliseconds
  if($live) {
   Start-Sleep -Milliseconds 500
   $port.Write([string][char]27)
   $reply+=Wait-CameraText 'soc> ' 5
  }
  $status=[regex]::Match($reply,'status=(?:0x)?([0-9a-fA-F]{8})')
  $results.Add([pscustomobject]@{attempt=$attempt;live=$live;startup_ms=$elapsed;status=if($status.Success){$status.Groups[1].Value}else{$null};safe_prompt=$reply.Contains('soc> ')})
  Write-Output "CAMERA_START_SAMPLE attempt=$attempt live=$live startup_ms=$elapsed"
  Start-Sleep -Milliseconds 300
 }
} finally {
 if($port.IsOpen){$port.Close()};$port.Dispose()
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($EvidencePrefix+'.log'),$transcript.ToString(),(New-Object Text.UTF8Encoding($false)))
 $receipt=[ordered]@{scope='ROM debug camera start + Esc, no capture or media write';attempts=$results.ToArray();failures=@($results | Where-Object {!$_.live -or !$_.safe_prompt}).Count;observed_at_utc=[DateTime]::UtcNow.ToString('o')}
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($EvidencePrefix+'.json'),($receipt | ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
}
if($results.Count -ne $Attempts -or $receipt.failures){throw 'CAMERA_START_REPRO_FAIL; see exact status in evidence'}
Write-Output 'CAMERA_START_REPRO_PASS'
