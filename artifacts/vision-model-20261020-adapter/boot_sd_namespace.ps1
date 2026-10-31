param([string]$PackageDirectory=$PSScriptRoot,[string]$PortName='COM5',
      [string]$LogPath,[switch]$PreflightOnly)
$ErrorActionPreference='Stop'
$package=[IO.Path]::GetFullPath($PackageDirectory)
$manifest=Get-Content -LiteralPath (Join-Path $package 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($manifest.format_profile -cne 'picture-new-sd-namespace-v1'){throw 'Unexpected private SD package'}
foreach($entry in $manifest.private_files.PSObject.Properties){
 $path=Join-Path (Join-Path $package 'sd-root') $entry.Name
 if((Get-Item -LiteralPath $path).Length -ne $entry.Value.bytes -or
    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value.sha256){throw ('Private package identity mismatch: '+$entry.Name)}
}
if($PreflightOnly){Write-Output 'PICTURE_NEW_SD_MENU_PREFLIGHT_PASS recurring_uart_file_upload=0';return}
if(-not $LogPath){
 $logs=Join-Path $package 'logs';New-Item -ItemType Directory -Force -Path $logs | Out-Null
 $LogPath=Join-Path $logs ('boot-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'.log')
}
$LogPath=[IO.Path]::GetFullPath($LogPath)
if(Test-Path -LiteralPath $LogPath){throw 'Choose a fresh boot transcript'}
$serial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=200;$serial.WriteTimeout=1000
$capture=[Text.StringBuilder]::new();$script:remaining=''
function Send-Paced([string]$Text){foreach($c in $Text.ToCharArray()){$serial.Write([string]$c);Start-Sleep -Milliseconds 3}}
function Wait-Text([string]$Marker,[int]$Seconds){
 $part=[Text.StringBuilder]::new();[void]$part.Append($script:remaining);$script:remaining=''
 $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
 while([DateTime]::UtcNow -lt $deadline){
  $text=$part.ToString()
  if($text -match 'XQ_BOOT_MENU_FAIL|XQ_BOOT_MENU_REJECT|SD payload invalid|SD payload CRC mismatch|SD load failed|SD_LOADER_FAIL|Kernel panic|XQ_MODEL_START_FAILED'){throw 'SD menu/boot failed; no files were uploaded or written'}
  $at=$text.IndexOf($Marker,[StringComparison]::Ordinal)
  if($at -ge 0){$script:remaining=$text.Substring($at+$Marker.Length);return}
  $chunk=$serial.ReadExisting()
  if($chunk){[void]$part.Append($chunk);[void]$capture.Append($chunk);Write-Host -NoNewline $chunk}
  Start-Sleep -Milliseconds 100
 }
 throw ('Bounded SD boot timeout waiting for '+$Marker)
}
try{
 $serial.Open();Send-Paced "`r"
 Wait-Text 'soc> ' 10;Send-Paced "info`r";Wait-Text 'soc> ' 10
 if($capture.ToString() -notmatch 'CPU_HZ=59400000 TIMEBASE_HZ=49500000'){throw 'Load the matching volatile E8 before this SD candidate'}
 Send-Paced "xqboot`r";Wait-Text 'bootmenu> ' 30
 $loader=[regex]::Escape($manifest.layout.loader)
 $choice=[regex]::Match($capture.ToString(),'(?m)^([1-8]) [A-Za-z0-9_-]+ \['+$loader+'\]\r?$')
 if(-not $choice.Success){throw 'SD menu does not register this private loader'}
 Send-Paced ($choice.Groups[1].Value+"`r");Wait-Text 'XQ LINUX PIKAFISH READY' 420
 $text=$capture.ToString()
 foreach($entry in $manifest.compiled_six_payload_descriptors.PSObject.Properties){
  if($text -notmatch ('Loading '+[regex]::Escape($entry.Name)+' bytes='+$entry.Value.bytes+'[\s\S]*?CRC32=0x'+$entry.Value.crc32)){
   throw ('Missing private SD CRC proof: '+$entry.Name)
  }
 }
 if($text -notmatch 'rv32-driver-quantized-mac.*camera=background'){throw 'Strict native camera runtime proof absent'}
 Write-Output 'PICTURE_NEW_SD_MENU_BOOT_PASS recurring_uart_file_upload=0 sd_written=0 flash_written=0'
}finally{
 if($serial.IsOpen){$serial.Close()};$serial.Dispose()
 [IO.File]::WriteAllText($LogPath,$capture.ToString(),[Text.UTF8Encoding]::new($false))
}
