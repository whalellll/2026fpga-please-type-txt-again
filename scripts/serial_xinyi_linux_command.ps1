param(
 [Parameter(Mandatory=$true)][string]$CommandFile,
 [Parameter(Mandatory=$true)][string]$LogPath,
 [ValidateRange(1,600)][int]$TimeoutSeconds=60,
 [ValidatePattern('^COM[0-9]+$')][string]$SerialPortName='COM5'
)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $LogPath){throw 'Preserve previous UART evidence'}
$token=[Guid]::NewGuid().ToString('N').Substring(0,10)
$nonce='XYHOST_'+$token
$command=[IO.File]::ReadAllText([IO.Path]::GetFullPath($CommandFile)).Replace("`r`n","`n").Replace("`r","`n").Replace("`n","`r")
if($command.Length -gt 32768){throw 'Command text bound'}
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'build/picture-tools/uart_pacing.ps1')
[BoardUartPacing]::DelayUs=6000
$port=[IO.Ports.SerialPort]::new($SerialPortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.ReadTimeout=200;$port.WriteTimeout=10000;$port.DtrEnable=$false;$port.RtsEnable=$false
$transcript=[Text.StringBuilder]::new()
function Until([string]$marker,[int]$seconds){
 $seen=[Text.StringBuilder]::new();$deadline=[DateTime]::UtcNow.AddSeconds($seconds)
 while([DateTime]::UtcNow -lt $deadline){
  $part=$port.ReadExisting()
  if($part){
   [void]$transcript.Append($part);[void]$seen.Append($part)
   if($transcript.Length -gt 2000000){throw 'UART text bound'}
   if($seen.ToString().Contains($marker)){return $seen.ToString()}
  }else{Start-Sleep -Milliseconds 20}
 }
 throw ('Timeout waiting for '+$marker+'; remote execution was not cancelled')
}
try{
 $port.Open();Send-Paced "`r";[void](Until '/ # ' 10)
 Send-Paced ("stty -echo`rprintf 'XYHOST_%s_READY\n' '$token'`r")
 [void](Until ($nonce+'_READY') 15)
 # The receipt runs in the parent shell. Explicit exit and set -e inside the
 # command shell cannot suppress it, unlike the old in-heredoc receipt.
 $framed="{`rsh <<'${nonce}_BODY'`r"+$command+"`r${nonce}_BODY`r"+
  'xyhost_rc=$?'+"`rprintf 'XYHOST_%s_STATUS=%s\nXYHOST_%s_DONE_END\n' '$token' "+
  '"$xyhost_rc"'+" '$token'`r}`r"
 Send-Paced $framed
 $result=Until ($nonce+'_DONE_END') $TimeoutSeconds
 Write-Output $result
 $status=[regex]::Match($result,[regex]::Escape($nonce)+'_STATUS=([0-9]+)')
 if(!$status.Success){throw 'Missing parent-shell command status'}
 if([int]$status.Groups[1].Value -ne 0){throw ('Remote command exited '+$status.Groups[1].Value)}
}finally{
 if($port.IsOpen){
  try{Send-Paced ("stty echo`rprintf 'XYHOST_%s_RESTORED\n' '$token'`r");[void](Until ($nonce+'_RESTORED') 10)}catch{}
  $port.Close()
 }
 $port.Dispose()
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($LogPath),$transcript.ToString(),[Text.UTF8Encoding]::new($false))
}
