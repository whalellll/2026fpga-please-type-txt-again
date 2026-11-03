param([Parameter(Mandatory=$true)][string]$Binary,
 [Parameter(Mandatory=$true)][ValidatePattern('^/run/xinyi-[A-Za-z0-9.-]+\z')][string]$Remote,
 [Parameter(Mandatory=$true)][string]$LogPath,
 [Parameter(Mandatory=$true)][string]$ProgramReceipt,
 [Parameter(Mandatory=$true)][string]$HelpersManifest)
$ErrorActionPreference='Stop'
$file=[IO.Path]::GetFullPath($Binary);$log=[IO.Path]::GetFullPath($LogPath)
if(Test-Path $log){throw 'Fresh UART evidence required'}
$data=Get-Item -LiteralPath $file
if($data.Length -lt 1 -or $data.Length -gt 4194304){throw 'RAM upload is bounded to 4 MiB'}
$expected=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
$program=Get-Content $ProgramReceipt -Raw -Encoding UTF8|ConvertFrom-Json
$manifest=Get-Content $HelpersManifest -Raw -Encoding UTF8|ConvertFrom-Json
if($program.status -cne 'PASS' -or $program.bitstream_sha256 -cne '9ba02f105d6168e9445e9a15e2f7a1093d885229deae9e268994acdbe29f5ea1'){throw 'Actual CPU60 program receipt required'}
$receiver=$manifest.files.'linux-xmodem'.sha256
if($receiver -notmatch '^[0-9a-f]{64}\z'){throw 'Receiver identity required'}
Add-Type -TypeDefinition @'
using System;using System.IO;using System.IO.Ports;using System.Text;using System.Threading;using System.Diagnostics;
using System.Runtime.InteropServices;
public static class XinyiRamLink {
 [DllImport("winmm.dll")]static extern uint timeBeginPeriod(uint n);
 [DllImport("winmm.dll")]static extern uint timeEndPeriod(uint n);
 static StringBuilder log=new StringBuilder();static Stopwatch total=new Stopwatch();
 static int Read(SerialPort p){if(total.Elapsed.TotalMinutes>15)throw new TimeoutException("RAM deployment bound");try{return p.ReadByte();}catch(TimeoutException){return -1;}}
 static void Note(int n){if(n==9||n==10||n==13||n>=32&&n<127){if(log.Length>1000000)throw new IOException("UART text bound");log.Append((char)n);}}
 static void Pace(SerialPort p,string s){foreach(char c in s){p.Write(c.ToString());Thread.Sleep(2);}}
 static string Until(SerialPort p,string marker,int seconds){
  var text=new StringBuilder();var end=DateTime.UtcNow.AddSeconds(seconds);
  while(DateTime.UtcNow<end){int n=Read(p);if(n<0)continue;Note(n);text.Append((char)n);string s=text.ToString();
   if(s.Contains("XINYI_LINUX_RAM_RX_FAIL"))throw new IOException("RAM receiver rejected");
   if(s.Contains(marker))return s;if(text.Length>8192)text.Remove(0,4096);
  }throw new TimeoutException("Waiting for "+marker);
 }
 static int Control(SerialPort p){var end=DateTime.UtcNow.AddSeconds(8);while(DateTime.UtcNow<end){int n=Read(p);if(n==6||n==21||n==24||n==67)return n;if(n>=0)Note(n);}throw new TimeoutException("XMODEM ACK");}
 static void Slice(SerialPort p,byte[] data,int offset,int bytes){
  if(Control(p)!=67)throw new IOException("Missing CRC invitation");
  for(int at=0;at<bytes;at+=1024){
   byte[] packet=new byte[1029];packet[0]=2;packet[1]=(byte)(at/1024+1);packet[2]=(byte)(255-packet[1]);int crc=0;
   for(int i=0;i<1024;i++){byte b=at+i<bytes?data[offset+at+i]:(byte)26;packet[i+3]=b;crc^=b<<8;for(int k=0;k<8;k++)crc=((crc&32768)!=0?(crc<<1)^0x1021:crc<<1)&65535;}
   packet[1027]=(byte)(crc>>8);packet[1028]=(byte)crc;bool ack=false;
   for(int tries=0;tries<4&&!ack;tries++){
    for(int j=0;j<packet.Length;j+=8){p.Write(packet,j,Math.Min(8,packet.Length-j));Thread.Sleep(6);}
    int response=Control(p);if(response==24)throw new IOException("Receiver cancelled");ack=response==6;
   }if(!ack)throw new IOException("Packet retry limit offset="+(offset+at));
  }
  p.Write(new byte[]{4},0,1);if(Control(p)!=6)throw new IOException("Missing EOT ACK");
 }
 public static void Run(string file,string remote,string expected,string receiver,string path){
  byte[] data=File.ReadAllBytes(file);bool raw=false;timeBeginPeriod(1);total.Start();double reported=0;
  using(var p=new SerialPort("COM5",115200,Parity.None,8,StopBits.One)){
   p.ReadTimeout=100;p.WriteTimeout=10000;p.DtrEnable=false;p.RtsEnable=false;p.Handshake=Handshake.None;
   try{
    p.Open();Pace(p,"\r");Until(p,"/ # ",10);Pace(p,"stty -echo\r");Until(p,"/ # ",10);
    Pace(p,"sha256sum /run/xinyi-linux-xmodem-r01\r");string checkedRx=Until(p,"/ # ",30);
    if(!checkedRx.Contains(receiver+"  /run/xinyi-linux-xmodem-r01"))throw new IOException("Receiver SHA changed");
    Pace(p,"test ! -e "+remote+" && test ! -e "+remote+".part && printf 'XINYI_RAM_TARGET_ABSENT\\n'\r");
    if(!Until(p,"/ # ",10).Contains("XINYI_RAM_TARGET_ABSENT"))throw new IOException("RAM target exists");
    Pace(p,"/run/xinyi-linux-xmodem-r01 "+remote+" "+data.Length+"\r");raw=true;
    for(int offset=0;offset<data.Length;offset+=65536){
     int bytes=Math.Min(65536,data.Length-offset);
     Until(p,"XINYI_LINUX_RX_CHUNK offset="+offset+" bytes="+bytes+"\n",30);
     Until(p,"Start PN03 XMODEM-CRC slice...\n",10);Slice(p,data,offset,bytes);
     if(total.Elapsed.TotalSeconds-reported>=60 || offset+bytes==data.Length){
      string value="bytes="+(offset+bytes)+"/"+data.Length+" elapsed="+total.Elapsed.TotalSeconds.ToString("F1")+"s";
      Console.WriteLine("XINYI_RAM_UPLOAD "+value);File.WriteAllText(path+".progress.txt",value);reported=total.Elapsed.TotalSeconds;
     }
    }
    Until(p,"XINYI_LINUX_RAM_RX_PASS bytes="+data.Length,30);raw=false;Until(p,"/ # ",10);
    Pace(p,"sha256sum "+remote+"\r");string answer=Until(p,"/ # ",90);
    if(!answer.Contains(expected+"  "+remote))throw new IOException("Actual RAM upload SHA mismatch");
    Console.WriteLine("XINYI_RAM_UPLOAD_SHA_PASS "+remote+" sha256="+expected);
   }finally{
    if(p.IsOpen){if(raw){try{p.Write(new byte[]{24,24},0,2);Thread.Sleep(300);}catch{}}try{Pace(p,"stty echo\r");}catch{}p.Close();}
    File.WriteAllText(path,log.ToString(),new UTF8Encoding(false));timeEndPeriod(1);
   }
  }
 }
}
'@
[XinyiRamLink]::Run($file,$Remote,$expected,$receiver,$log)
if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected){throw 'Local software changed during transfer'}
$record=@{status='RAM_UPLOAD_SHA_PASS';bytes=$data.Length;binary_sha256=$expected;remote=$Remote;
 receiver_sha256=$receiver;program_receipt_sha256=(Get-FileHash $ProgramReceipt -Algorithm SHA256).Hash.ToLowerInvariant();
 host_script_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();
 uart_log_sha256=(Get-FileHash $log -Algorithm SHA256).Hash.ToLowerInvariant();sd_written=$false;flash_written=$false}
[IO.File]::WriteAllText($log+'.json',($record|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
