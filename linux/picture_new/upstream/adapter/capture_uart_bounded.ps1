param([string]$PortName='COM5',[Parameter(Mandatory=$true)][string]$LogPath,
      [ValidateRange(5,180)][int]$Seconds=100)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $LogPath){throw 'Use a fresh UART transcript'}
$serial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=200
$transcript=[Text.StringBuilder]::new()
try {
    $serial.Open();Write-Output 'UART_CAPTURE_READY'
    $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    while([DateTime]::UtcNow -lt $deadline){
        $chunk=$serial.ReadExisting()
        if($chunk){[void]$transcript.Append($chunk);Write-Host -NoNewline $chunk}
        Start-Sleep -Milliseconds 150
    }
} finally {
    if($serial.IsOpen){$serial.Close()};$serial.Dispose()
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($LogPath),$transcript.ToString(),[Text.UTF8Encoding]::new($false))
}
