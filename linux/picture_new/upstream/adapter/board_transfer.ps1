param([ValidateSet('upload','download','command')][string]$Operation,
      [string]$LocalPath,[string]$RemotePath,[string]$Command,
      [string]$PortName='COM5',[int]$TimeoutSeconds=300,[string]$TranscriptPath)
$ErrorActionPreference='Stop'
if($TranscriptPath -and (Test-Path -LiteralPath $TranscriptPath)){throw 'Choose a fresh transfer transcript'}
if(-not ('XqModelTransfer' -as [type])){
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.IO.Ports;
using System.Diagnostics;
using System.Text;
public static class XqModelTransfer {
 static SerialPort port; static Stopwatch total; static int timeout;
 static int Byte(){
  while(total.Elapsed.TotalSeconds<timeout){try{return port.ReadByte();}catch(TimeoutException){}}
  throw new TimeoutException("Bounded UART operation timed out");
 }
 static string Until(string needle){
  var s=new StringBuilder();
  while(true){try{s.Append((char)Byte());}catch(TimeoutException){throw new TimeoutException("Waiting for "+needle+"; recent="+s.ToString());}
   if(s.ToString().EndsWith(needle,StringComparison.Ordinal))return s.ToString();
   if(s.Length>16384)s.Remove(0,8192);}
 }
 static void Paced(string text){
  foreach(char c in text){port.Write(c.ToString());long end=Stopwatch.GetTimestamp()+Stopwatch.Frequency/500;
   while(Stopwatch.GetTimestamp()<end){}}
 }
 static uint Crc(byte[] b){uint c=0xffffffff;
  foreach(byte v in b){c^=v;for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0u);}return c^0xffffffff;
 }
 public static string Run(string device,string op,string local,string remote,string command,int seconds){
  port=new SerialPort(device,115200,Parity.None,8,StopBits.One);
  port.DtrEnable=false;port.RtsEnable=false;port.ReadTimeout=100;port.WriteTimeout=15000;
  timeout=seconds;total=Stopwatch.StartNew();
  try{
   port.Open();port.DiscardInBuffer();Paced("\r");Until("/ # ");Paced("stty -echo\r");Until("/ # ");
   if(op=="command"){
    Paced("( "+command+" ); xq_rc=$?; printf '\\nXQ_ADAPTER_DONE=%s\\n' \"$xq_rc\"\r");
    string result=Until("XQ_ADAPTER_DONE=")+Until("/ # ");
    if(!result.Contains("XQ_ADAPTER_DONE=0"))throw new IOException(result);
    return result;
   }
   byte[] payload=op=="upload"?File.ReadAllBytes(local):null;
   uint expected=payload!=null?Crc(payload):0;
   Paced("/tmp/xq-transfer "+(op=="upload"?"receive "+remote+" "+payload.Length+" "+expected.ToString("x8"):"send "+remote)+"\r");
   Until("XQT1 ");string header=Until("\n").Trim();string[] fields=header.Split(' ');
   int length=int.Parse(fields[0]);uint check=Convert.ToUInt32(fields[1],16);
   if(length<=0 || length>32*1024*1024)throw new IOException("Bad transfer size");
   if(op=="upload" && (length!=payload.Length || check!=expected))throw new IOException("Transfer identity mismatch");
   if(payload==null)payload=new byte[length];
   for(int offset=0;offset<length;offset+=1024){int n=Math.Min(1024,length-offset);
    if(op=="upload"){
     // Frozen LiteUART RX is a 16-byte FIFO polled by Linux at HZ250.
     // Bound bursts to eight bytes and allow a timer tick to drain them.
     for(int j=0;j<n;j+=8){port.Write(payload,offset+j,Math.Min(8,n-j));
      long until=Stopwatch.GetTimestamp()+Stopwatch.Frequency/200;
      while(Stopwatch.GetTimestamp()<until){} }
     if(Byte()!=6)throw new IOException("Bad chunk ACK");}
    else{for(int j=0;j<n;j++)payload[offset+j]=(byte)Byte();port.Write(new byte[]{6},0,1);}
   }
   string end=Until("XQ_TRANSFER_EXIT=")+Until("/ # ");
   if(!end.Contains("XQ_TRANSFER_EXIT=0") || Crc(payload)!=check)throw new IOException("Transfer CRC/exit failure");
   if(op=="download"){using(var f=new FileStream(local,FileMode.CreateNew,FileAccess.Write)){f.Write(payload,0,payload.Length);}}
   return "XQ_TRANSFER_PASS operation="+op+" bytes="+length+" crc32="+check.ToString("x8")+" elapsed_ms="+total.ElapsedMilliseconds;
  }finally{
   if(port.IsOpen){try{Paced("stty echo\r");Until("/ # ");}catch{}port.Close();}port.Dispose();
  }
 }
}
'@
}
if($Operation -ne 'command'){
 if($RemotePath -notmatch '^/(run|tmp)/[A-Za-z0-9_./-]+$' -or $RemotePath.Contains('..')){throw 'Only safe RAM paths allowed'}
 $LocalPath=[IO.Path]::GetFullPath($LocalPath)
 if($Operation -eq 'download' -and (Test-Path -LiteralPath $LocalPath)){throw 'Choose a fresh local download path'}
}
try {
 $result=[XqModelTransfer]::Run($PortName,$Operation,$LocalPath,$RemotePath,$Command,$TimeoutSeconds)
 if($TranscriptPath){[IO.File]::WriteAllText([IO.Path]::GetFullPath($TranscriptPath),$result+"`n",[Text.UTF8Encoding]::new($false))}
 $result
} catch {
 if($TranscriptPath){
  $detail=if($_.Exception.InnerException){$_.Exception.InnerException.Message}else{$_.Exception.Message}
  [IO.File]::WriteAllText([IO.Path]::GetFullPath($TranscriptPath),$detail+"`n",[Text.UTF8Encoding]::new($false))
 }
 throw
}
