param([string]$PortName='COM5',[Parameter(Mandatory=$true)][string]$OutputPath,
      [switch]$BlockingRead,[ValidateSet('info','prompt')][string]$Probe='info')
$ErrorActionPreference='Stop'
if($PortName -cne 'COM5'){throw 'Only the identified CP210x COM5 is in scope'}
if(Test-Path -LiteralPath $OutputPath){throw 'Choose a fresh diagnostic receipt'}
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class XqNativeUartProbe {
 [StructLayout(LayoutKind.Sequential)] public struct DCB {
  public uint length,baud,flags; public ushort reserved,xonLimit,xoffLimit;
  public byte bytes,parity,stop,xon,xoff,error,eof,evt; public ushort reserved1;
 }
 [StructLayout(LayoutKind.Sequential)] public struct Timeouts {public uint interval,multiplier,constant,writeMultiplier,writeConstant;}
 [StructLayout(LayoutKind.Sequential)] public struct Stat {public uint flags,input,output;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFile(string name,uint access,uint share,IntPtr security,uint creation,uint flags,IntPtr template);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetCommState(SafeFileHandle h,ref DCB state);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetCommState(SafeFileHandle h,ref DCB state);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetCommTimeouts(SafeFileHandle h,ref Timeouts state);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool ClearCommError(SafeFileHandle h,out uint errors,out Stat stat);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetCommModemStatus(SafeFileHandle h,out uint status);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadFile(SafeFileHandle h,byte[] bytes,uint count,out uint got,IntPtr overlapped);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool WriteFile(SafeFileHandle h,byte[] bytes,uint count,out uint sent,IntPtr overlapped);
 static void Check(bool okay){if(!okay)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());}
 public static string Run(string name,bool blocking,string probe){
  using(var h=CreateFile(@"\\.\"+name,0xc0000000,0,IntPtr.Zero,3,0,IntPtr.Zero)){
   if(h.IsInvalid)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
   var before=new DCB();before.length=(uint)Marshal.SizeOf(typeof(DCB));Check(GetCommState(h,ref before));
   var after=before;after.baud=115200;after.flags=1;after.bytes=8;after.parity=0;after.stop=0;after.xon=17;after.xoff=19;
   // Binary, no hardware/software flow control, DTR and RTS remain deasserted.
   Check(SetCommState(h,ref after));Check(GetCommState(h,ref after));
   var timeout=new Timeouts{interval=blocking?50u:0xffffffff,constant=blocking?1500u:0u,writeConstant=1000};Check(SetCommTimeouts(h,ref timeout));
   uint errors,modem,allErrors=0,sent;Stat state;Check(ClearCommError(h,out errors,out state));allErrors|=errors;
   byte[] command=Encoding.ASCII.GetBytes(probe=="prompt"?"\r":"info\r");Check(WriteFile(h,command,(uint)command.Length,out sent,IntPtr.Zero));
   var data=new MemoryStream();byte[] buffer=new byte[4096];var deadline=DateTime.UtcNow.AddSeconds(5);
   while(DateTime.UtcNow<deadline){uint got;Check(ReadFile(h,buffer,(uint)buffer.Length,out got,IntPtr.Zero));
    if(got>0)data.Write(buffer,0,(int)got);Check(ClearCommError(h,out errors,out state));allErrors|=errors;Thread.Sleep(50);}
   Check(GetCommModemStatus(h,out modem));
   byte[] result=data.ToArray();string escaped=Encoding.ASCII.GetString(result).Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r","\\r").Replace("\n","\\n").Replace("\t","\\t");
   return "{\"dcb_bytes\":"+Marshal.SizeOf(typeof(DCB))+",\"baud_before\":"+before.baud+",\"flags_before\":"+before.flags+
    ",\"baud_after\":"+after.baud+",\"flags_after\":"+after.flags+",\"transmitted_bytes\":"+sent+
    ",\"received_bytes\":"+result.Length+",\"comm_errors\":"+allErrors+",\"queued_rx\":"+state.input+
    ",\"queued_tx\":"+state.output+",\"modem_status\":"+modem+",\"text\":\""+escaped+"\"}";
  }
 }
}
'@
$json=[XqNativeUartProbe]::Run($PortName,$BlockingRead.IsPresent,$Probe)
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),$json+"`n",[Text.UTF8Encoding]::new($false))
$json
if(($json|ConvertFrom-Json).received_bytes -eq 0){exit 2}
