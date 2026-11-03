param([string]$ToolchainRoot='', [string]$CandidateDirectory='build/picture-candidate', [switch]$UartPayloads,[switch]$UartKernel,[switch]$SdConsoleEntry,[switch]$CameraRetry=$true)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$saved=$env:PATH
try {
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
 if (!(Test-Path -LiteralPath (Join-Path $out 'picture_payloads.h'))) { throw 'Prepare candidate DTB and SD contract first.' }
 if (!$out.StartsWith(([IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Loader output must stay in the ignored build/ candidate directory.'
 }
 $src=Join-Path $repo 'sw/bootloader'
 $loader=Join-Path $repo 'linux/boot/v2_1_sd/source'
 $args=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
 '-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections',
 '-O2','-Wall','-Wextra','-Werror','-DSD_LOADER_PICTURE_BOOT=1','-I',$src,'-I',$out)
 if ($UartPayloads) { $args += '-DSD_LOADER_PICTURE_UART_PAYLOADS=1' }
 if ($UartKernel) {
  if(!$UartPayloads){throw 'UART kernel requires UART payload mode'}
  $args += '-DSD_LOADER_PICTURE_UART_KERNEL=1'
 }
 $sources=@((Join-Path $loader 'start.S'),(Join-Path $loader 'loader.c'))
 if($CameraRetry){
  $args+=@('-DSD_LOADER_PICTURE_RETRY_CAMERA=1','-I',(Join-Path $repo 'linux/vision'),'-I',(Join-Path $repo 'sw/xiangqi'))
  $sources+=Join-Path $loader 'picture_camera_boot.c'
  $sources+=Join-Path $repo 'linux/vision/xq_camera.c'
  $sources+=Join-Path $repo 'linux/vision/xq_camera_retry.c'
 }
 foreach($name in @('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','camera.c')) { $sources+=Join-Path $src $name }
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'loader-obj') -Sources $sources -CompilerArguments $args
 if($SdConsoleEntry -and $UartPayloads){throw 'SD console entry reads every payload from SD'}
 $stem=if ($SdConsoleEntry) {'loader-picture-sdboot'} elseif ($UartPayloads) {'loader-picture-uart-candidate'} else {'loader-picture-candidate'}
 $link=Join-Path $loader 'link.ld'
 if($SdConsoleEntry){
  $link=Join-Path $out 'sdboot.ld'
  $text=(Get-Content (Join-Path $loader 'link.ld') -Raw).Replace('ORIGIN = 0x01000000','ORIGIN = 0x00000000')
  [IO.File]::WriteAllText($link,$text,(New-Object Text.UTF8Encoding($false)))
 }
 $elf=Join-Path $out ($stem+'.elf')
 $savedAction=$ErrorActionPreference
 try {
  $ErrorActionPreference='Continue'
  & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax' `
   "-Wl,-T,$link" @objects $tc.Libgcc -o $elf 2>&1 | ForEach-Object { $_.ToString() }
  $linkExit=$LASTEXITCODE
 } finally { $ErrorActionPreference=$savedAction }
 if($linkExit) { throw 'Picture RAM loader link failed' }
 $null=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 & $tc.objcopy -O binary $elf (Join-Path $out ($stem+'.bin'))
 if($LASTEXITCODE) { throw 'Picture RAM loader objcopy failed' }
 Write-Output 'PICTURE_RAM_LOADER_BUILD_PASS board_validated=false'
} finally { $env:PATH=$saved }
