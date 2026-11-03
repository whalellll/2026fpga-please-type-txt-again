param([Parameter(Mandatory=$true)][string]$LocalPath,
      [Parameter(Mandatory=$true)][string]$RemotePath,
      [Parameter(Mandatory=$true)][string]$ReceiptPath,
      [string]$PortName='COM5',[int]$TimeoutSeconds=240)
$ErrorActionPreference='Stop'
if($RemotePath -notmatch '^/tmp/[a-z0-9-]+$'){throw 'Bootstrap targets must be simple /tmp paths'}
if(Test-Path -LiteralPath $ReceiptPath){throw 'Use a fresh bootstrap receipt'}
$LocalPath=[IO.Path]::GetFullPath($LocalPath)
$original=[IO.File]::ReadAllBytes($LocalPath)
if($original.Length -lt 1 -or $original.Length -gt 131072){throw 'Bootstrap is for small RAM helpers only'}
$hash=(Get-FileHash -LiteralPath $LocalPath -Algorithm SHA256).Hash.ToLowerInvariant()
$compressed=[IO.MemoryStream]::new()
$gzip=[IO.Compression.GZipStream]::new($compressed,[IO.Compression.CompressionMode]::Compress,$true)
$gzip.Write($original,0,$original.Length);$gzip.Dispose()
$payload=$compressed.ToArray();$compressed.Dispose()
$hasher=[Security.Cryptography.SHA256]::Create()
try{$gzipHash=([BitConverter]::ToString($hasher.ComputeHash($payload))).Replace('-','').ToLowerInvariant()}finally{$hasher.Dispose()}
Add-Type -TypeDefinition @'
using System;
using System.IO.Ports;
using System.Diagnostics;
using System.Text;
public static class XqRamBootstrap {
 static SerialPort port; static Stopwatch total; static int timeout;
 static string Prompt(){
  var s=new StringBuilder();
  while(total.Elapsed.TotalSeconds<timeout){
   try{s.Append((char)port.ReadByte());}catch(TimeoutException){}
   if(s.ToString().EndsWith("/ # ",StringComparison.Ordinal))return s.ToString();
   if(s.Length>8192)s.Remove(0,4096);
  }
  throw new TimeoutException("Bounded RAM bootstrap timeout; recent="+s.ToString());
 }
 static void Paced(string command){
  for(int i=0;i<command.Length;i+=2){
   port.Write(command.Substring(i,Math.Min(2,command.Length-i)));
   long end=Stopwatch.GetTimestamp()+Stopwatch.Frequency/500;
   while(Stopwatch.GetTimestamp()<end){}
  }
 }
 static string Command(string text){Paced(text+"\r");return Prompt();}
 public static string Run(string device,byte[] packed,string remote,string packedHash,string hash,int seconds){
  port=new SerialPort(device,115200,Parity.None,8,StopBits.One);
  port.DtrEnable=false;port.RtsEnable=false;port.ReadTimeout=100;port.WriteTimeout=5000;
  timeout=seconds;total=Stopwatch.StartNew();
  try{
   port.Open();Paced("\r");Prompt();Command("stty -echo");
   string seed=remote+".bootstrap.gz";
   string start=Command("if test ! -e "+remote+" && test ! -e "+seed+"; then : > "+seed+"; echo XQ_BOOTSTRAP_NEW; fi");
   if(!start.Contains("XQ_BOOTSTRAP_NEW"))throw new Exception("RAM bootstrap path already exists");
   string encoded=Convert.ToBase64String(packed);int count=(encoded.Length+511)/512;
   for(int i=0;i<count;i++){
    string part=encoded.Substring(i*512,Math.Min(512,encoded.Length-i*512));
    string ack="XQ_BOOT_CHUNK_"+i;
    string reply=Command("printf '%s' '"+part+"' | base64 -d >> "+seed+" && echo "+ack);
    if(!reply.Contains(ack))throw new Exception("RAM bootstrap chunk failed "+i);
    if((i+1)%16==0 || i+1==count)System.Console.WriteLine("RAM_BOOTSTRAP_PROGRESS "+(i+1)+"/"+count);
   }
   string packedProof=Command("sha256sum "+seed);
   if(!packedProof.Contains(packedHash))throw new Exception("RAM bootstrap gzip SHA mismatch");
   string proof=Command("gzip -dc "+seed+" > "+remote+" && chmod 700 "+remote+" && sha256sum "+remote);
   if(!proof.Contains(hash))throw new Exception("RAM helper executable SHA mismatch");
   return proof+"\nRAM_BOOTSTRAP_PASS elapsed_ms="+total.ElapsedMilliseconds;
  }finally{
   if(port.IsOpen){try{Command("stty echo");}catch{}port.Close();}port.Dispose();
  }
 }
}
'@
$proof=[XqRamBootstrap]::Run($PortName,$payload,$RemotePath,$gzipHash,$hash,$TimeoutSeconds)
if((Get-FileHash -LiteralPath $LocalPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash){throw 'Local helper changed'}
$receipt=[ordered]@{status='PASS';operation='RAM_helper_bootstrap';local_path=$LocalPath;
    remote_path=$RemotePath;bytes=$original.Length;sha256=$hash;gzip_bytes=$payload.Length;gzip_sha256=$gzipHash;proof=$proof}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($ReceiptPath),($receipt|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
$proof
