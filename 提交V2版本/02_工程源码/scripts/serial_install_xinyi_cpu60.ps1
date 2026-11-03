param(
 [ValidateSet('Probe','Receive','Install')][string]$Stage='Probe',
 [Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$LogPath,
 [string]$ProgramReceipt='build/xinyi-one-20261024/cram-functional-r01.json',
 [string]$ProbeReceipt,
 [string]$TestsReceipt,
 [switch]$FromInstaller
)
$ErrorActionPreference='Stop'
$hostScriptSha=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath($CandidateDirectory)
$log=[IO.Path]::GetFullPath($LogPath)
if(Test-Path $log){throw 'Fresh UART evidence required'}
$contract=Get-Content (Join-Path $out 'install_contract.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$program=Get-Content $ProgramReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if($program.status -cne 'PASS' -or $program.bitstream_sha256 -cne $contract.bitstream_sha256 -or
 $contract.media_sectors -ne 62333952 -or $contract.partition_lba -ne 32){throw 'Program/media identity mismatch'}
foreach($input in $contract.source_inputs.PSObject.Properties){
 if((Get-FileHash -LiteralPath $input.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $input.Value.sha256){throw "Source changed: $($input.Name)"}
}
$paths=@();foreach($f in $contract.files){
 $p=Join-Path $out ('payloads/'+$f.name)
 if((Get-Item $p).Length -ne $f.bytes -or (Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $f.sha256){throw 'Payload mismatch'}
 $paths+=$p
}
$installer=Join-Path $out 'PN03INST.BIN'
$installerSha=(Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$cid=''
if($FromInstaller -and $Stage -ne 'Probe'){throw 'FromInstaller only applies to a read-only replacement probe'}
if($Stage -ne 'Probe'){
 if(!$ProbeReceipt){throw 'Fresh actual probe required'}
 $probe=Get-Content $ProbeReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
 if($probe.status -cne 'PROBE_PASS_READ_ONLY' -or $probe.installer_sha256 -cne $installerSha -or
  $probe.program_receipt_sha256 -cne (Get-FileHash $ProgramReceipt -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'Probe mismatch'}
 $cid=$probe.cid
 if($Stage -eq 'Install'){
  if(!$TestsReceipt){throw 'Passed offline tests required before media writes'}
  $tests=Get-Content $TestsReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
  if($tests.status -cne 'PASS' -or $tests.installer_sha256 -cne $installerSha){throw 'Tests mismatch'}
 }
}
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.IO.Ports;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class Pn03InstallLink {
 [DllImport("winmm.dll")] static extern uint timeBeginPeriod(uint p);
 [DllImport("winmm.dll")] static extern uint timeEndPeriod(uint p);
 static readonly StringBuilder log=new StringBuilder();
 static Stopwatch total=new Stopwatch();static string progress;
 static readonly Dictionary<string,byte[]> content=new Dictionary<string,byte[]>();
 static readonly Dictionary<string,Stopwatch> watches=new Dictionary<string,Stopwatch>();
 static readonly Dictionary<string,double> reports=new Dictionary<string,double>();
 static readonly HashSet<string> phases=new HashSet<string>();
 static void Note(int n){if(n==9||n==10||n==13||n>=32&&n<127){if(log.Length>=4000000)throw new IOException("UART text limit");log.Append((char)n);}}
 static int Read(SerialPort p){if(total.Elapsed.TotalHours>3)throw new TimeoutException("Three hour deployment limit");try{return p.ReadByte();}catch(TimeoutException){return -1;}}
 static void Pace(SerialPort p,string s){foreach(char c in s){p.Write(c.ToString());Thread.Sleep(2);}}
 static string Until(SerialPort p,string needle,int seconds){
  var part=new StringBuilder();var end=DateTime.UtcNow.AddSeconds(seconds);
  while(DateTime.UtcNow<end){int n=Read(p);if(n<0)continue;Note(n);part.Append((char)n);string s=part.ToString();
   if(Regex.IsMatch(s,@"PN03_INSTALL_FAIL code=[0-9]+\r?\n")||s.Contains("PN03_INSTALL_TARGET_REJECTED")||s.Contains("PN03_REPAIR_REQUIRED")||s.Contains("Kernel panic")||s.Contains("XINYI_PN03_LOAD_OR_CRC_FAIL")||s.Contains("XINYI_PLATFORM_IDENTITY_REJECTED")||s.Contains("XINYI_RUNTIME_START_FAILED")){
    // Preserve the error value and bounded rollback output before closing RX.
    Console.WriteLine("PN03_BOARD_REJECTION_DRAIN");
    var drain=Stopwatch.StartNew();var tail=new StringBuilder();
    while(drain.Elapsed.TotalSeconds<70){
     int extra=Read(p);if(extra<0)continue;Note(extra);tail.Append((char)extra);
     string ending=tail.ToString();
     if(ending.Contains("PN03_FAILURE_CLEANUP_COMPLETE")||ending.Contains("PN03_REPAIR_REQUIRED")||ending.Contains("soc> "))break;
     if(tail.Length>4096)tail.Remove(0,2048);
    }
    throw new IOException("Board rejected; complete bounded UART evidence: "+s);
   }
   foreach(string tag in new string[]{"PN03_PAIR_COMMITTED","PN03_OLD_BOOT_FILES_AND_SELECTOR_PRESERVED","XINYI_PN03_TARGET_ROM_CODE_PASS","XINYI_PN03_SIX_CRC_PASS","LINUX_BOOT_TO_SHELL_SECONDS=","XINYI_FUNCTIONAL_CANDIDATE"})
    if(s.Contains(tag)&&phases.Add(tag)){Console.WriteLine("PN03_BOARD_PHASE "+tag);File.WriteAllText(progress,"phase="+tag+Environment.NewLine);}
   if(s.Contains(needle))return s;if(part.Length>8192)part.Remove(0,4096);
  }throw new TimeoutException("UART waiting for "+needle);
 }
 static int Control(SerialPort p){var end=DateTime.UtcNow.AddSeconds(8);while(DateTime.UtcNow<end){int n=Read(p);if(n==6||n==21||n==24||n==67)return n;if(n>=0)Note(n);}throw new TimeoutException("XMODEM control");}
 static void Send(SerialPort p,string file,int begin,int count){
  if(!content.ContainsKey(file))content[file]=File.ReadAllBytes(file);
  byte[] data=content[file];if(begin<0||count<=0||count>65536||begin>data.Length-count)throw new IOException("Invalid slice");
  int blocks=(count+1023)/1024,retries=0;
  if(Control(p)!=67)throw new IOException("Missing XMODEM CRC invitation");
  if(!watches.ContainsKey(file)){watches[file]=Stopwatch.StartNew();reports[file]=-60;}
  var watch=watches[file];
  for(int i=0;i<blocks;i++){
   byte[] packet=new byte[1029];packet[0]=2;packet[1]=(byte)(i+1);packet[2]=(byte)(255-packet[1]);int crc=0;
   for(int j=0;j<1024;j++){int at=i*1024+j;byte b=at<count?data[begin+at]:(byte)26;packet[j+3]=b;crc^=b<<8;for(int k=0;k<8;k++)crc=((crc&32768)!=0?(crc<<1)^0x1021:crc<<1)&65535;}
   packet[1027]=(byte)(crc>>8);packet[1028]=(byte)crc;bool ack=false;
   for(int attempt=0;attempt<4&&!ack;attempt++){
    for(int at=0;at<packet.Length;at+=64){p.Write(packet,at,Math.Min(64,packet.Length-at));Thread.Sleep(6);}
    int response=Control(p);if(response==24)throw new IOException("Board cancelled XMODEM");if(response==6)ack=true;else retries++;
   }
   if(!ack)throw new IOException("XMODEM retry bound");
   int completed=begin+Math.Min(count,(i+1)*1024);
   if(watch.Elapsed.TotalSeconds-reports[file]>=60||completed==data.Length){
    string status=String.Format("file={0} bytes={1}/{2} elapsed={3:F1}s retries={4}",Path.GetFileName(file),completed,data.Length,watch.Elapsed.TotalSeconds,retries);
    File.WriteAllText(progress,status+Environment.NewLine);Console.WriteLine("PN03_UART "+status);reports[file]=watch.Elapsed.TotalSeconds;
   }
  }
  p.Write(new byte[]{4},0,1);if(Control(p)!=6)throw new IOException("Missing XMODEM EOT ACK");
  log.AppendLine("PN03_UART_SLICE_PASS "+Path.GetFileName(file)+" offset="+begin+" bytes="+count+" retries="+retries);
 }
 public static string Run(string stage,string installer,string[] files,string path,string cid,bool fromInstaller){
  total.Start();progress=path+".progress.txt";timeBeginPeriod(1);
  using(var p=new SerialPort("COM5",115200,Parity.None,8,StopBits.One)){
   p.ReadTimeout=100;p.WriteTimeout=10000;p.DtrEnable=false;p.RtsEnable=false;p.Handshake=Handshake.None;
   try{p.Open();
    if(stage=="Probe"){
     Pace(p,fromInstaller?"console\r":"\r");Until(p,"soc> ",10);Pace(p,"info\r");string info=Until(p,"soc> ",10);
     if(!info.Contains("CPU_HZ=60000000")||!info.Contains("MAC_ID=0x50464e31"))throw new IOException("Wrong CPU60 board");
     Pace(p,"loadx 0x01800000\r");Until(p,"Start XMODEM-CRC transfer now...",10);Send(p,installer,0,(int)new FileInfo(installer).Length);Until(p,"soc> ",10);
     Pace(p,"boot 0x01800000\r");Until(p,"pn03> ",300);
     Match m=Regex.Match(log.ToString(),@"PN03_INSTALL_CID=([0-9a-f]{32}) sectors=62333952 partition_lba=32");
     if(!m.Success||!log.ToString().Contains("PN03_PROBE_PASS"))throw new IOException("No exact card/probe receipt");
     Console.WriteLine("PN03_READ_ONLY_PROBE_PASS");return m.Groups[1].Value;
    }
    Pace(p,"\r");Until(p,"pn03> ",10);Pace(p,"receive\r");
    // Already verified aliases need no UART data. Every pending request names
    // one of the exact, SHA-checked candidate files; no unbounded file request.
    int recoveries=0;
    for(int count=0;count<4096;count++){
     var part=new StringBuilder();string value="";var end=DateTime.UtcNow.AddSeconds(10);bool ready=false,requested=false;
     while(DateTime.UtcNow<end){int n=Read(p);if(n<0)continue;Note(n);part.Append((char)n);value=part.ToString();
      if(value.Contains("PN03_INSTALL_FAIL")||value.Contains("PN03_REPAIR_REQUIRED"))throw new IOException("Receive rejected");
      if(value.Contains("pn03> ")){
       if(value.Contains("PN03_UART_RETRYABLE")){if(++recoveries>8)throw new IOException("Slice recovery bound");Pace(p,"receive\r");part.Length=0;continue;}
       ready=true;break;
      }
      Match m=Regex.Match(value,@"PN03_RECEIVE_CHUNK ([A-Z0-9.]+) offset=([0-9]+) bytes=([0-9]+)\r?\n");
      if(m.Success){string selected=null;foreach(string f in files)if(Path.GetFileName(f)==m.Groups[1].Value)selected=f;
       requested=true;
       int offset=Int32.Parse(m.Groups[2].Value),bytes=Int32.Parse(m.Groups[3].Value);
       if(selected==null||offset%65536!=0||offset<0||offset>=new FileInfo(selected).Length||bytes!=Math.Min(65536,new FileInfo(selected).Length-offset))throw new IOException("Unknown payload slice");
       Until(p,"Start PN03 XMODEM-CRC slice...",10);
       try{Send(p,selected,offset,bytes);}
       catch(Exception e){
        if(!(e is IOException)&&!(e is TimeoutException))throw;
        if(++recoveries>8)throw;p.Write(new byte[]{24,24},0,2);Until(p,"pn03> ",15);Pace(p,"receive\r");
       }
       break;}
     }
     if(ready)break;if(!requested)throw new TimeoutException("Receive slice request");if(count==4095)throw new IOException("Receive request limit");
    }
    if(stage=="Receive"){Console.WriteLine("PN03_ALL_PAYLOADS_IN_RAM_CRC_PASS_NO_SD_WRITES");return cid;}
    Pace(p,"install "+cid+"\r");Until(p,"PN03_OLD_BOOT_FILES_AND_SELECTOR_PRESERVED",300);Until(p,"pn03> ",10);
    Console.WriteLine("PN03_CREATE_ONLY_INSTALL_AND_READBACK_PASS");
    Pace(p,"boot\r");Until(p,"XINYI_FUNCTIONAL_CANDIDATE",900);
    Console.WriteLine("PN03_LINUX_PRODUCT_STARTUP_OBSERVED");return cid;
   }catch{if(p.IsOpen){try{p.Write(new byte[]{24,24},0,2);}catch{}}throw;}
   finally{if(p.IsOpen)p.Close();File.WriteAllText(path,log.ToString(),new UTF8Encoding(false));timeEndPeriod(1);}
  }
 }
}
'@
$observed=[Pn03InstallLink]::Run($Stage,$installer,$paths,$log,$cid,[bool]$FromInstaller)
$record=@{status=$(if($Stage -eq 'Probe'){'PROBE_PASS_READ_ONLY'}elseif($Stage -eq 'Receive'){'RAM_RECEIVE_CRC_PASS_NO_SD_WRITES'}else{'INSTALL_AND_PRODUCT_STARTUP_PASS'});
 host_script_sha256=$hostScriptSha;
 cid=$observed;installer_sha256=$installerSha;program_receipt_sha256=(Get-FileHash $ProgramReceipt -Algorithm SHA256).Hash.ToLowerInvariant();
 install_contract_sha256=(Get-FileHash (Join-Path $out 'install_contract.json') -Algorithm SHA256).Hash.ToLowerInvariant();
 uart_log_sha256=(Get-FileHash $log -Algorithm SHA256).Hash.ToLowerInvariant();sd_written=($Stage -eq 'Install');selector_modified=$false;flash_written=$false}
[IO.File]::WriteAllText($log+'.json',($record|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
