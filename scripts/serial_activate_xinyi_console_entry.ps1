param(
 [Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$ProgramReceipt,
 [Parameter(Mandatory=$true)][string]$SdInstallReceipt,
 [Parameter(Mandatory=$true)][string]$TestsReceipt,
 [Parameter(Mandatory=$true)][string]$LogPath
)
$ErrorActionPreference='Stop'
$out=[IO.Path]::GetFullPath($CandidateDirectory);$log=[IO.Path]::GetFullPath($LogPath)
foreach($p in @($log,$log+'.loader.txt',$log+'.return-rom.txt',$log+'.json')){if(Test-Path -LiteralPath $p){throw 'Fresh evidence paths required'}}
$contract=Get-Content (Join-Path $out 'entry_contract.json') -Raw -Encoding UTF8|ConvertFrom-Json
$program=Get-Content $ProgramReceipt -Raw -Encoding UTF8|ConvertFrom-Json
$sd=Get-Content $SdInstallReceipt -Raw -Encoding UTF8|ConvertFrom-Json
$tests=Get-Content $TestsReceipt -Raw -Encoding UTF8|ConvertFrom-Json
$image=Join-Path $out 'entry-installer.bin';$imageSha=(Get-FileHash $image -Algorithm SHA256).Hash.ToLowerInvariant()
if($program.status -cne 'PASS' -or $program.operation -cne 'CRAM' -or $program.audit_profile -cne 'PublishedE42' -or
 $program.device_count -ne 1 -or $program.bitstream_sha256 -cne $contract.bitstream_sha256 -or
 $sd.status -cne 'INSTALL_ONLY_READBACK_PASS' -or $sd.cid -cne $contract.cid -or
 $sd.program_receipt_sha256 -cne (Get-FileHash $ProgramReceipt -Algorithm SHA256).Hash.ToLowerInvariant() -or
 $tests.status -cne 'PASS' -or $tests.installer_sha256 -cne $imageSha){throw 'Exact program/card/installation/test identity required'}
foreach($input in $contract.source_inputs.PSObject.Properties){
 if((Get-FileHash -LiteralPath $input.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $input.Value.sha256){throw 'Entry source drift'}
}
foreach($input in $tests.source_sha256.PSObject.Properties){
 if((Get-FileHash -LiteralPath $input.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $input.Value){throw 'Entry test input drift'}
}
$transcript=[Text.StringBuilder]::new()
function New-BoardPort{
 $p=[IO.Ports.SerialPort]::new('COM5',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
 $p.DtrEnable=$false;$p.RtsEnable=$false;$p.Handshake=[IO.Ports.Handshake]::None
 $p.ReadTimeout=200;$p.WriteTimeout=10000;return $p
}
function Send-PacedText([IO.Ports.SerialPort]$p,[string]$s){foreach($ch in $s.ToCharArray()){$p.Write([string]$ch);Start-Sleep -Milliseconds 3}}
function Wait-Text([IO.Ports.SerialPort]$p,[string]$needle,[int]$seconds){
 $part=[Text.StringBuilder]::new();$end=[DateTime]::UtcNow.AddSeconds($seconds)
 while([DateTime]::UtcNow -lt $end){
  $s=$p.ReadExisting()
  if($s){[void]$part.Append($s);[void]$transcript.Append($s)
   if($transcript.Length -gt 2097152){throw 'UART text bound'}
   if($part.ToString() -match 'SD_CONSOLE_FAIL|SD_CONSOLE_REPAIR_REQUIRED|Kernel panic|LOAD_OR_CRC_FAIL|TARGET_REJECTED|XINYI_RUNTIME_START_FAILED'){throw 'Board rejected; preserve backup and full evidence'}
   if($part.ToString().Contains($needle)){return}
  }else{Start-Sleep -Milliseconds 20}
 }
 throw ('Timeout waiting for '+$needle)
}
# The create-only installer still owns the console. Return without booting it.
$port=New-BoardPort
try{$port.Open();Send-PacedText $port "`r";Wait-Text $port 'pn03> ' 10;Send-PacedText $port "console`r";Wait-Text $port 'soc> ' 20}
finally{if($port.IsOpen){$port.Close()};$port.Dispose();[IO.File]::WriteAllText($log+'.return-rom.txt',$transcript.ToString(),[Text.UTF8Encoding]::new($false))}
$transcript.Clear()|Out-Null
& (Join-Path $PSScriptRoot 'serial_boot_v2_1_sd.ps1') -PortName COM5 -ImagePath $image -LoadAddress 0x01800000 -LogPath ($log+'.loader.txt') -SuccessMarker SD_CONSOLE_READY -FailureMarkers @('SD_CONSOLE_FAIL','Kernel panic') -TimeoutSeconds 40
if($LASTEXITCODE){throw 'Entry updater failed to start'}
$port=New-BoardPort
try{
 $port.Open();Send-PacedText $port "`r";Wait-Text $port 'sdentry> ' 10
 Send-PacedText $port "install`r";Wait-Text $port 'SD_CONSOLE_INSTALL_PASS' 120
 Write-Host 'ENTRY_BACKUP_AND_COMPLETE_ALIAS_READBACK_PASS'
 Send-PacedText $port "console`r";Wait-Text $port 'soc> ' 20
 # No loadx/XMODEM/file transfer after this point. Only the requested command.
 Send-PacedText $port "xqboot`r";Wait-Text $port 'XINYI_GUI_FIRST_PRESENTED' 420
 $text=$transcript.ToString()
 if(!$text.Contains('XINYI_PN15_SEVEN_CRC_PASS') -or !$text.Contains('Linux version 5.14') -or
    !$text.Contains('XINYI_FUNCTIONAL_CANDIDATE cpu_hz=60000000')){throw 'Incomplete standalone startup evidence'}
 $actual=[regex]::Match($text,'SD_CONSOLE_IMAGE_READBACK_PASS name=xiangqi.bin bytes=([0-9]+) crc=0x([0-9a-f]+)')
 if(!$actual.Success -or [int]$actual.Groups[1].Value -ne $contract.expected_patched.bytes -or
    $actual.Groups[2].Value -cne $contract.expected_patched.crc32){throw 'Complete alias readback mismatch'}
 $record=@{status='ROM_XQBOOT_PN15_LINUX_GUI_STARTED';cid=$contract.cid;manual_command='xqboot';
  uart_payloads_after_console=0;flash_written=$false;sd_written=$true;selector_modified=$false;
  original=$contract.original;expected_patched=$contract.expected_patched;backup_name=$contract.backup_name;
  loader=$contract.loader;installer_sha256=$imageSha;physical_layout_acceptance=$false;
  bitstream_sha256=$contract.bitstream_sha256;new_recognition_quality_accepted=$false}
 [IO.File]::WriteAllText($log+'.json',($record|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host 'ROM_XQBOOT_LINUX_GUI_PASS uart_payloads_after_console=0 flash_written=false'
}finally{if($port.IsOpen){$port.Close()};$port.Dispose();[IO.File]::WriteAllText($log,$transcript.ToString(),[Text.UTF8Encoding]::new($false))}
