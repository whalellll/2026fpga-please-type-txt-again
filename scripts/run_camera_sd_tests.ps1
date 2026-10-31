param([string]$HostGccPath='D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
 [string]$PythonPath='D:\LJL\WORK\Anaconda3\python.exe')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$temp=Join-Path ([IO.Path]::GetTempPath()) ('soc_camera_sd_'+[guid]::NewGuid().ToString('N'))
$exe=$temp+'.exe';$png=Join-Path $temp 'IMG00001.PNG';$json=Join-Path $temp 'IMG00001.JSON';$savedPath=$env:PATH
New-Item -ItemType Directory -Path $temp | Out-Null
try {
 $env:PATH=(Split-Path -Parent $HostGccPath)+[IO.Path]::PathSeparator+$savedPath
 Push-Location $root
 try {
  & $HostGccPath -std=c99 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections '-Wl,--gc-sections' -I sw/bootloader `
   sw/bootloader/fat_ro.c sw/bootloader/fat_camera.c sw/bootloader/png_rgb565.c `
   sw/bootloader/crc32_fast.c sw/bootloader/camera_sd.c sim/camera_sd_file_test.c -o $exe
  if($LASTEXITCODE){throw 'Camera SD host compile failed'}
  & $exe $png
  if($LASTEXITCODE){throw 'Camera SD FAT fault regression failed'}
  & $PythonPath sim/test_camera_sd_png.py $png
  if($LASTEXITCODE){throw 'Camera SD independent PNG validation failed'}
  & (Join-Path $PSScriptRoot 'verify_camera_sd.ps1') -Directory $temp
 } finally {Pop-Location}
} finally {
 $env:PATH=$savedPath
 foreach($path in @($exe,$png,$json)){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}}
 if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Force} # empty directory only
}
