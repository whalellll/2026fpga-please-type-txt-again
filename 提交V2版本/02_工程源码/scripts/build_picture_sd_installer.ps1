param([string]$ToolchainRoot='',[Parameter(Mandatory=$true)][string]$CandidateDirectory)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if(!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Installer output must stay in build/'}
if(!(Test-Path (Join-Path $out 'picture_install_payloads.h'))){throw 'Prepare the exact install contract first'}
$saved=$env:PATH
try{
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $src=Join-Path $repo 'sw/bootloader';$loader=Join-Path $repo 'linux/boot/v2_1_sd/source'
 $privateFat=Join-Path $loader 'picture_fat_write'
 $link=(Get-Content (Join-Path $loader 'link.ld') -Raw).Replace('ORIGIN = 0x01000000','ORIGIN = 0x01800000')
 [IO.File]::WriteAllText((Join-Path $out 'installer.ld'),$link,(New-Object Text.UTF8Encoding($false)))
 $args=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
  '-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections',
  '-O2','-Wall','-Wextra','-Werror','-I',$privateFat,'-I',$src,'-I',$out)
 $sources=@((Join-Path $loader 'start.S'),(Join-Path $loader 'install_picture.c'))
 $sources+=Join-Path $privateFat 'fat_camera.c'
 foreach($name in @('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c')){$sources+=Join-Path $src $name}
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'installer-obj') -Sources $sources -CompilerArguments $args
 $elf=Join-Path $out 'installer-picture.elf'
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax' "-Wl,-T,$out/installer.ld" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'Installer link failed'}
 $null=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 & $tc.objcopy -O binary $elf (Join-Path $out 'installer-picture.bin')
 if($LASTEXITCODE){throw 'Installer objcopy failed'}
 Write-Output 'PICTURE_SD_INSTALLER_BUILD_PASS board_validated=false'
}finally{$env:PATH=$saved}
