param(
 [string]$PortName='COM5',
 [Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$LogPath,
 [switch]$Boot,
 [switch]$ReturnToConsole
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$log=[IO.Path]::GetFullPath($LogPath)
if(Test-Path -LiteralPath $log){throw 'Choose a fresh install log'}
$contract=Get-Content (Join-Path $out 'install_contract.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($contract.schema_version -ne 1 -or @($contract.files).Count -ne 4){throw 'Invalid create-only install contract'}
$paths=New-Object 'Collections.Generic.List[string]'
foreach($entry in $contract.files){
 $path=[IO.Path]::GetFullPath($entry.path)
 if(!$path.StartsWith($out+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
  $entry.name -notmatch '^[A-Z0-9_]{1,8}\.[A-Z0-9_]{1,3}$' -or
  (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or
  (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256){throw 'Install input identity mismatch'}
 $paths.Add($path)
}
$installer=Join-Path $out 'installer-picture.bin'
if(!(Test-Path -LiteralPath $installer)){throw 'Build the exact installer first'}
if(-not ('PictureSdInstall' -as [type])){
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.IO.Ports;
using System.Text;
using System.Diagnostics;
using System.Text.RegularExpressions;
public static class PictureSdInstall {
 static readonly StringBuilder transcript=new StringBuilder();
 static Stopwatch total;
 static void Note(int x){if(x==9||x==10||x==13||(x>=32&&x<127))transcript.Append((char)x);}
 static int Read(SerialPort p){
  if(total.Elapsed.TotalSeconds>1800)throw new TimeoutException("Install exceeded 30 minutes");
  try{return p.ReadByte();}catch(TimeoutException){return -1;}
 }
 static void Until(SerialPort p,string text,int seconds){
  var end=DateTime.UtcNow.AddSeconds(seconds);var recent=new StringBuilder();
  while(DateTime.UtcNow<end){int x=Read(p);if(x<0)continue;Note(x);recent.Append((char)x);
   string value=recent.ToString();
   if(value.Contains("SD_INSTALL_FAIL")||value.Contains("REPAIR_REQUIRED")||value.Contains("CRC mismatch")||value.Contains("Kernel panic"))
    throw new IOException("Board failure: "+value);
   if(value.EndsWith(text,StringComparison.Ordinal))return;
   if(recent.Length>4096)recent.Remove(0,2048);
  }throw new TimeoutException("Waiting for "+text);
 }
 static int Control(SerialPort p,int seconds){
  var end=DateTime.UtcNow.AddSeconds(seconds);
  while(DateTime.UtcNow<end){int x=Read(p);if(x==6||x==21||x==24||x==67)return x;if(x>=0)Note(x);}
  throw new TimeoutException("XMODEM control timeout");
 }
 static void Send(SerialPort p,string path){
  byte[] content=File.ReadAllBytes(path);int blocks=(content.Length+1023)/1024;
  if(Control(p,10)!=67)throw new IOException("Missing XMODEM CRC invitation");
  var watch=Stopwatch.StartNew();double report=0;int retries=0;
  for(int index=0;index<blocks;index++){
   byte[] packet=new byte[1029];packet[0]=2;packet[1]=(byte)(index+1);packet[2]=(byte)(255-packet[1]);int crc=0;
   for(int j=0;j<1024;j++){
    int at=index*1024+j;byte b=at<content.Length?content[at]:(byte)26;packet[j+3]=b;crc^=b<<8;
    for(int k=0;k<8;k++)crc=((crc&32768)!=0?((crc<<1)^0x1021):(crc<<1))&65535;
   }
   packet[1027]=(byte)(crc>>8);packet[1028]=(byte)crc;bool ack=false;
   for(int attempt=0;attempt<5&&!ack;attempt++){
    p.Write(packet,0,packet.Length);int response=Control(p,8);
    if(response==24)throw new IOException("Board cancelled XMODEM");
    if(response==6)ack=true;else retries++;
   }
   if(!ack)throw new IOException("XMODEM retry limit");
   if(watch.Elapsed.TotalSeconds-report>=60){
    Console.WriteLine("SD_INSTALL_UART {0}: {1}/{2} blocks elapsed={3:F0}s",Path.GetFileName(path),index+1,blocks,watch.Elapsed.TotalSeconds);
    report=watch.Elapsed.TotalSeconds;
   }
  }
  p.Write(new byte[]{4},0,1);if(Control(p,10)!=6)throw new IOException("Missing end ACK");
  string line=String.Format("SD_INSTALL_UART_PASS file={0} bytes={1} elapsed={2:F1}s retries={3}",Path.GetFileName(path),content.Length,watch.Elapsed.TotalSeconds,retries);
  transcript.AppendLine(line);Console.WriteLine(line);
 }
 public static string Run(string port,string installer,string[] files,string log,bool boot,bool console){
  total=Stopwatch.StartNew();string cid="";
  using(var p=new SerialPort(port,115200,Parity.None,8,StopBits.One)){
   p.ReadTimeout=200;p.WriteTimeout=10000;p.DtrEnable=false;p.RtsEnable=false;p.Handshake=Handshake.None;
   try{
    p.Open();p.DiscardInBuffer();p.Write("\r");Until(p,"soc> ",10);
    p.Write("loadx 0x01800000\r");Until(p,"Start XMODEM-CRC transfer now...",10);
    Send(p,installer);Until(p,"soc> ",10);p.Write("boot 0x01800000\r");Until(p,"install> ",20);
    Match m=Regex.Match(transcript.ToString(),@"SD_INSTALL_CID=([0-9a-f]{32}) sectors=([0-9]+) partition_lba=([0-9]+)");
    if(!m.Success)throw new IOException("Missing freshly checked card CID");cid=m.Groups[1].Value;
    Console.WriteLine("SD_INSTALL_TARGET_CID="+cid);
    p.Write("receive\r");
    foreach(string path in files){
     string name=Path.GetFileName(path);Until(p,"SD_INSTALL_RECEIVE "+name,10);Send(p,path);
     Until(p,"SD_INSTALL_RAM_CRC_PASS "+name,20);
    }
    Until(p,"install> ",20);p.Write("install "+cid+"\r");Until(p,"SD_INSTALL_COMMAND_PASS",180);Until(p,"install> ",10);
    string all=transcript.ToString();
    if(Regex.Matches(all,"SD_INSTALL_READBACK_CRC_PASS ").Count!=4||Regex.Matches(all,"SD_INSTALL_PAIR_COMMITTED").Count!=2)
     throw new IOException("Incomplete readback/commit receipt");
    Console.WriteLine("PICTURE_SD_CREATE_ONLY_INSTALL_PASS files=4 old_files_preserved=true");
    if(boot){p.Write("bootlinux\r");Until(p,"XQ LINUX PIKAFISH READY",420);Console.WriteLine("PICTURE_BOOT_FROM_SD_PASS");}
    else if(console){p.Write("console\r");Until(p,"soc> ",20);Console.WriteLine("PICTURE_INSTALL_RETURN_CONSOLE_PASS");}
    return cid;
   }catch{if(p.IsOpen){try{p.Write(new byte[]{24,24},0,2);}catch{}}throw;}
   finally{if(p.IsOpen)p.Close();File.WriteAllText(log,transcript.ToString(),new UTF8Encoding(false));}
  }
 }
}
'@
}
if($Boot -and $ReturnToConsole){throw 'Choose Boot or ReturnToConsole'}
$cid=[PictureSdInstall]::Run($PortName,$installer,$paths.ToArray(),$log,[bool]$Boot,[bool]$ReturnToConsole)
$receipt=@{schema_version=1;scope='Picture SD candidate deployment, NOT BoardRelease';
 status='PASS';cid=$cid;media_sectors=$contract.media_sectors;partition_lba=$contract.partition_lba;
 files=$contract.files;existing_files_preserved=$true;flash_written=$false;boot_from_sd=[bool]$Boot;
 install_contract_sha256=(Get-FileHash (Join-Path $out 'install_contract.json') -Algorithm SHA256).Hash.ToLowerInvariant();
 installer_sha256=(Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant();
 uart_log_sha256=(Get-FileHash $log -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText(($log+'.json'),($receipt|ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
