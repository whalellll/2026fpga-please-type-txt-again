param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
if(!('CameraSdVerify' -as [type])){
 Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.IO;
using System.Drawing;
public static class CameraSdVerify {
 static readonly uint[] table=MakeTable();
 static uint[] MakeTable(){uint[] t=new uint[256];for(uint i=0;i<256;i++){uint c=i;for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0);t[i]=c;}return t;}
 static uint Byte(uint c,byte b){return table[(c^b)&255]^(c>>8);}
 public static string FileCrc(string path){uint c=0xffffffff;using(FileStream s=File.OpenRead(path)){byte[] b=new byte[65536];int n;while((n=s.Read(b,0,b.Length))>0)for(int i=0;i<n;i++)c=Byte(c,b[i]);}return (c^0xffffffff).ToString("x8");}
 public static string RawCrc(string path){uint c=0xffffffff;using(Bitmap b=new Bitmap(path)){
  if(b.Width!=1280||b.Height!=720)throw new Exception("PNG dimensions");
  for(int y=0;y<720;y++)for(int x=0;x<1280;x++){Color p=b.GetPixel(x,y);int r=p.R>>3,g=p.G>>2,blue=p.B>>3;
   if(p.A!=255||p.R!=((r<<3)|(r>>2))||p.G!=((g<<2)|(g>>4))||p.B!=((blue<<3)|(blue>>2)))throw new Exception("Pixel is not original RGB565 expansion");
   int v=(r<<11)|(g<<5)|blue;c=Byte(c,(byte)v);c=Byte(c,(byte)(v>>8));
  }
 }return (c^0xffffffff).ToString("x8");}
}
'@
}
$files=@(Get-ChildItem -LiteralPath $Directory -File -Filter IMG?????.PNG)
if(!$files.Count){throw 'No SD camera PNG files found'}
foreach($file in $files){
 $json=[IO.Path]::ChangeExtension($file.FullName,'.JSON')
 if(!(Test-Path -LiteralPath $json -PathType Leaf)){throw "Missing metadata: $json"}
 $meta=[IO.File]::ReadAllText($json)|ConvertFrom-Json
 if($meta.width -ne 1280 -or $meta.height -ne 720 -or $meta.source -ne 'CMOS2' -or
    $meta.pixel_format -ne 'RGB565LE' -or $meta.row_order -ne 'top-to-bottom' -or
    $meta.captured_at -ne $null -or $meta.PSObject.Properties.Name -match 'label|chess'){throw "Unexpected metadata: $json"}
 if([CameraSdVerify]::FileCrc($file.FullName) -cne $meta.png_crc32 -or
    [CameraSdVerify]::RawCrc($file.FullName) -cne $meta.raw_crc32){throw "PNG/raw CRC mismatch: $($file.FullName)"}
 Write-Output "SD_PNG_ALL_PIXELS_CRC_PASS frame=$($meta.frame) $($file.FullName)"
}
$temp=@(Get-ChildItem -LiteralPath $Directory -File | Where-Object{$_.Extension -in '.TMP','.part'})
if($temp.Count){throw "Unfinished files remain: $($temp.Name -join ', ')"}
Write-Output "SD_CARD_PNG_JSON_VERIFY_PASS images=$($files.Count)"
