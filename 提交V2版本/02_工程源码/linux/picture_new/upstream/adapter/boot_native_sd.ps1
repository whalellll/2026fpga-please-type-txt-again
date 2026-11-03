param([string]$PortName='COM5',[Parameter(Mandatory=$true)][string]$LogPath,
      [int]$TimeoutSeconds=420)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $LogPath){throw 'Use a fresh SD boot transcript'}
$serial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=200;$serial.WriteTimeout=1000
$transcript=[Text.StringBuilder]::new()
function Send-Paced([string]$Command){foreach($character in $Command.ToCharArray()){$serial.Write([string]$character);Start-Sleep -Milliseconds 3}}
function Until([string]$Marker,[int]$Seconds,[bool]$Booting=$false){
    $part=[Text.StringBuilder]::new();$deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    while([DateTime]::UtcNow -lt $deadline){
        $chunk=$serial.ReadExisting()
        if($chunk){
            [void]$part.Append($chunk);[void]$transcript.Append($chunk);Write-Host -NoNewline $chunk
            if($Booting -and $part.ToString() -match 'Kernel panic|SD payload invalid|SD payload CRC mismatch|SD load failed|SD_LOADER_FAIL|XQ_MODEL_START_FAILED|XQ_MODEL_START_FAILED|XQ_CAMERA_OWNER_FAIL'){
                throw 'Native SD boot reported a failure'
            }
            if($part.ToString().Contains($Marker)){return}
        }
        Start-Sleep -Milliseconds 100
    }
    throw ('Bounded boot timeout waiting for '+$Marker)
}
try{
    $serial.Open();Send-Paced "`r";Until 'soc> ' 15
    Send-Paced "info`r";Until 'soc> ' 15
    Send-Paced "sdinfo`r";Until 'soc> ' 25
    Send-Paced "xqboot`r";Until 'XQ LINUX PIKAFISH READY' $TimeoutSeconds $true
    $text=$transcript.ToString()
    foreach($pair in @(@('brfw.bin','8072b5c4'),@('N20K.BIN','57aec2e7'),@('N20FS.BIN','fd08270c'),
                       @('N20.DTB','4fb3265f'),@('pikafish.pff','80322636'),@('pikafish.atk','cba1dd72'))){
        $pattern='Loading '+[regex]::Escape($pair[0])+' bytes=[0-9]+[\s\S]*?CRC32=0x'+$pair[1]
        if($text -notmatch $pattern){throw ('SD payload CRC proof missing: '+$pair[0])}
    }
    if($text -notmatch 'rv32-driver-quantized-mac.*camera=background'){throw 'Strict native/background backend proof missing'}
    Write-Output "NATIVE_SD_BOOT_ENGINE_READY_PASS models_ready_requires_separate_probe=true"
}finally{
    if($serial.IsOpen){$serial.Close()};$serial.Dispose()
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($LogPath),$transcript.ToString(),[Text.UTF8Encoding]::new($false))
}
