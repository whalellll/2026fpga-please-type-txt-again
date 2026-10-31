param(
 [string]$PortName='COM5',
 [string]$CandidateDirectory='build/picture-candidate',
 [Parameter(Mandatory=$true)][string]$LogPath,
 [switch]$Boot,
 [switch]$VerifyExistingRootfs
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$candidate=[IO.Path]::GetFullPath((Join-Path $root $CandidateDirectory))
$log=[IO.Path]::GetFullPath($LogPath)
if(Test-Path -LiteralPath $log){throw 'Choose a fresh UART transfer log'}
$contract=Get-Content -LiteralPath (Join-Path $candidate 'sd_contract.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($entry in $contract.files.PSObject.Properties){
 $path=$entry.Value.path
 if(![IO.Path]::IsPathRooted($path)){$path=Join-Path $root $path}
 if((Get-Item -LiteralPath $path).Length -ne $entry.Value.bytes -or
    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value.sha256){
  throw "Candidate contract mismatch: $($entry.Name)"
 }
}
$loader=Join-Path $candidate 'loader-picture-uart-candidate.bin'
if(!(Test-Path -LiteralPath $loader)){throw 'Build the explicit -UartPayloads RAM loader first'}
if(-not ('PictureRamTransfer' -as [type])){
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.IO.Ports;
using System.Diagnostics;
using System.Text;
public static class PictureRamTransfer {
 static readonly StringBuilder transcript=new StringBuilder();
 static Stopwatch total;
 static int Read(SerialPort p) {
  if(total.Elapsed.TotalSeconds>2400)throw new TimeoutException("RAM transfer exceeded 40 minutes");
  try{return p.ReadByte();}catch(TimeoutException){return -1;}
 }
 static void Note(int x){if(x==9||x==10||x==13||(x>=32&&x<127))transcript.Append((char)x);}
 static void Until(SerialPort p,string needle,int seconds){
  var until=DateTime.UtcNow.AddSeconds(seconds);var recent=new StringBuilder();
  while(DateTime.UtcNow<until){int x=Read(p);if(x<0)continue;Note(x);recent.Append((char)x);
   if(recent.ToString().EndsWith(needle,StringComparison.Ordinal))return;
   if(recent.Length>4096)recent.Remove(0,2048);
  }throw new TimeoutException("Waiting for "+needle);
 }
 static int Control(SerialPort p,int seconds){
  var until=DateTime.UtcNow.AddSeconds(seconds);
  while(DateTime.UtcNow<until){int x=Read(p);if(x==6||x==21||x==24||x==67)return x;if(x>=0)Note(x);}
  throw new TimeoutException("Waiting for XMODEM control byte");
 }
 static void Send(SerialPort p,string path,string address){
  byte[] data=File.ReadAllBytes(path);int blocks=(data.Length+1023)/1024;
  p.Write("loadx "+address+"\r");Until(p,"Start XMODEM-CRC transfer now...",10);
  if(Control(p,10)!=67)throw new IOException("Missing XMODEM CRC invitation");
  var watch=Stopwatch.StartNew();double report=0;int retries=0;
  for(int index=0;index<blocks;index++){
   byte[] packet=new byte[1029];packet[0]=2;packet[1]=(byte)(index+1);packet[2]=(byte)(255-packet[1]);
   int crc=0;
   for(int j=0;j<1024;j++){
    int offset=index*1024+j;byte b=offset<data.Length?data[offset]:(byte)26;packet[j+3]=b;crc^=b<<8;
    for(int k=0;k<8;k++)crc=((crc&32768)!=0?((crc<<1)^0x1021):(crc<<1))&65535;
   }
   packet[1027]=(byte)(crc>>8);packet[1028]=(byte)crc;
   bool ack=false;
   for(int attempt=0;attempt<5&&!ack;attempt++){
    p.Write(packet,0,packet.Length);int response=Control(p,8);
    if(response==24)throw new IOException("Board cancelled XMODEM");
    if(response==6)ack=true;else retries++;
   }
   if(!ack)throw new IOException("XMODEM retry limit reached");
   if(watch.Elapsed.TotalSeconds-report>=60){
    Console.WriteLine("UART_RAM {0}: {1}/{2} blocks elapsed={3:F0}s",Path.GetFileName(path),index+1,blocks,watch.Elapsed.TotalSeconds);
    report=watch.Elapsed.TotalSeconds;
   }
  }
  p.Write(new byte[]{4},0,1);if(Control(p,8)!=6)throw new IOException("Missing end ACK");Until(p,"soc> ",10);
  string result=String.Format("UART_RAM_FILE_PASS file={0} bytes={1} address={2} elapsed_seconds={3:F1} retries={4}",Path.GetFileName(path),data.Length,address,watch.Elapsed.TotalSeconds,retries);
  transcript.AppendLine(result);Console.WriteLine(result);
 }
 public static void Run(string port,string rootfs,string dtb,string kernel,string log,bool verifyExisting){
  total=Stopwatch.StartNew();
  using(var p=new SerialPort(port,115200,Parity.None,8,StopBits.One)){
   p.ReadTimeout=200;p.WriteTimeout=10000;p.DtrEnable=false;p.RtsEnable=false;p.Handshake=Handshake.None;
   try{p.Open();p.DiscardInBuffer();p.Write("\r");Until(p,"soc> ",10);
    if(kernel!=null)Send(p,kernel,"0x00400000");
    if(!verifyExisting) Send(p,rootfs,"0x03000000");
    else {transcript.AppendLine("UART_RAM_ROOTFS_REUSE_UNTRUSTED; board loader must verify the full candidate CRC before boot");}
    Send(p,dtb,"0x1a000000");
   }catch{if(p.IsOpen){try{p.Write(new byte[]{24,24},0,2);}catch{}}throw;}
   finally{if(p.IsOpen)p.Close();File.WriteAllText(log,transcript.ToString(),new UTF8Encoding(false));}
  }
 }
}
'@
}
$rootfs=$contract.files.'brfs2.bin'.path
if(![IO.Path]::IsPathRooted($rootfs)){$rootfs=Join-Path $root $rootfs}
$kernel=$null
if($contract.uart_kernel){
 $kernel=$contract.files.Image.path
 if(![IO.Path]::IsPathRooted($kernel)){$kernel=Join-Path $root $kernel}
}
[PictureRamTransfer]::Run($PortName,$rootfs,(Join-Path $candidate 'br.dtb'),$kernel,$log,[bool]$VerifyExistingRootfs)
if($VerifyExistingRootfs){Write-Output 'PICTURE_DTB_RAM_PRELOAD_PASS rootfs=UNTRUSTED_UNTIL_BOARD_CRC sd_written=false flash_written=false'}
else{Write-Output 'PICTURE_UART_RAM_PRELOAD_PASS sd_written=false flash_written=false'}
if($Boot){
 & (Join-Path $PSScriptRoot 'serial_boot_v2_1_sd.ps1') -PortName $PortName -ImagePath $loader -LogPath ($log+'.boot.log') -TimeoutSeconds 420
}
