param([Parameter(Mandatory=$true)][ValidateSet('cold','warm')][string]$Group,
      [Parameter(Mandatory=$true)][ValidateRange(1,100)][int]$Pair,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [ValidateRange(60,7200)][int]$TimeoutSeconds=3600,
      [string]$PortName='COM5')
$ErrorActionPreference='Stop'
if($PortName -cne 'COM5'){throw 'Only the identified CP210x COM5 is in scope'}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
if($OutputDirectory -notlike "$([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../build')))\*") {throw 'Live receipts must stay under build'}
if(Test-Path -LiteralPath $OutputDirectory){throw 'Choose a new sample directory'}
[IO.Directory]::CreateDirectory($OutputDirectory)|Out-Null
if(-not ('XqCleanLatency' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.IO.Ports;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
public static class XqCleanLatency {
 static SerialPort port;static StreamWriter log;static Stopwatch clock;static int deadline;
 static void Send(string text) {
  foreach(char c in text+"\r") {
   port.Write(c.ToString());long end=Stopwatch.GetTimestamp()+Stopwatch.Frequency/500;
   while(Stopwatch.GetTimestamp()<end){}
  }
 }
 static string Until(string expression,int seconds) {
  var text=new StringBuilder();var timer=Stopwatch.StartNew();
  while(timer.Elapsed.TotalSeconds<seconds && clock.Elapsed.TotalSeconds<deadline) {
   string chunk=port.ReadExisting();
   if(chunk.Length==0){System.Threading.Thread.Sleep(50);continue;}
   log.Write(chunk);log.Flush();text.Append(chunk);
   if(text.Length>131072)throw new IOException("Unexpected verbose UART output");
   if(Regex.IsMatch(text.ToString(),expression,RegexOptions.Multiline))return text.ToString();
  }
  throw new TimeoutException("Bounded sample deadline; no following sample was triggered");
 }
 public static string Run(string device,string file,int seconds) {
  port=new SerialPort(device,115200,Parity.None,8,StopBits.One);
  port.DtrEnable=false;port.RtsEnable=false;port.ReadTimeout=100;port.WriteTimeout=5000;
  deadline=seconds+90;clock=Stopwatch.StartNew();bool echoOff=false,complete=false,started=false;
  using(log=new StreamWriter(file,false,new UTF8Encoding(false))) {
   try {
    port.Open();Send("");Until(@"/ # $",20);
    Send("stty -echo");Until(@"/ # $",20);echoOff=true;
    Send(". /etc/xq-picture.conf; test -p /run/xiangqi-pikafish.in && test ! -e \"$XQ_MODEL_DIRECTORY/request.txt\" && kill -0 $(cat /run/xiangqi-pikafish.pid) && kill -0 $(cat /run/xq-native-staging.pid) && echo XQ_CLEAN_PREFLIGHT_PASS");
    string ready=Until(@"/ # $",20);
    if(!ready.Contains("XQ_CLEAN_PREFLIGHT_PASS"))throw new IOException("GUI/worker idle preflight failed");
    Send("printf 'XQ_STATUS\\n' > /run/xiangqi-pikafish.in");
    string status=Until(@"XQ LINUX INJECT STATUS [^\r\n]*\r?\n",20);
    if(!Regex.IsMatch(status,@"\bengine=ready\b"))throw new IOException("GUI engine is not ready; no capture triggered");
    // The next command enters the existing production capture path. Until its
    // displayed terminal outcome there are no shell probes or data transfers.
    started=true;Send("printf 'XQ_PICTURE_CAPTURE\\n' > /run/xiangqi-pikafish.in");
    string result=Until(@"^XQ_PICTURE_LATENCY [^\r\n]*\r?\n",seconds);
    complete=true;
    Send("cat /run/xq-native-start.log; echo XQ_CLEAN_WORKER_END");
    string worker=Until(@"/ # $",20);
    if(!worker.Contains("XQ_CLEAN_WORKER_END"))throw new IOException("Worker log collection failed");
    return result+worker;
   } finally {
    if(port.IsOpen) {
     // Cancel/drain using the GUI's TERM handler if the bounded run failed.
     // Never trigger another capture after a timeout or user interruption.
     if(started && !complete) {
      try {Send("kill -TERM $(cat /run/xiangqi-pikafish.pid)");Until(@"/ # $",10);}catch{}
     }
     if(echoOff){try{Send("stty echo");Until(@"/ # $",10);}catch{}}
     port.Close();
    }
    port.Dispose();
   }
  }
 }
}
'@
}
$raw=Join-Path $OutputDirectory 'uart.log'
try {
 $result=[XqCleanLatency]::Run($PortName,$raw,$TimeoutSeconds)
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'completed.txt'),$result,[Text.UTF8Encoding]::new($false))
 $record=[ordered]@{status='RECORDED';group=$Group;pair=$Pair;trigger='software_FIFO_production_capture';physical_space_acceptance=$false;
  cold_definition='first fresh capture after worker and GUI restart; model startup excluded';
  active_interval_no_shell_probes=$true;observer=$false;extra_sha=$false;timeout_seconds=$TimeoutSeconds}
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'sample.json'),($record|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
 $result -split "`n" | Where-Object {$_ -match '^XQ_(NATIVE_(RECOGNITION|TIMING)|PICTURE_LATENCY) '}
} catch {
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'failed.txt'),($_|Out-String),[Text.UTF8Encoding]::new($false))
 throw
}
