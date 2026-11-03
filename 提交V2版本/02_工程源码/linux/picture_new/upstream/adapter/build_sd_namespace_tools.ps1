param([Parameter(Mandatory=$true)][string]$CandidateDirectory,
      [ValidateSet('menu','installer')][string]$Kind='menu',
      [string]$ToolchainRoot='D:/p17-gcc16-lto/native')
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $repo 'scripts/riscv_toolchain.ps1')
$out=[IO.Path]::GetFullPath($CandidateDirectory)
if(-not $out.StartsWith((Join-Path $repo 'build')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Use an isolated build/ output'}
$runtime=Join-Path $PSScriptRoot 'runtime';$boot=Join-Path $repo 'sw/bootloader'
$saved=$env:PATH
try {
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $flags=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
 '-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections',
 '-O2','-Wall','-Wextra','-Werror','-I',$boot,'-I',$runtime,'-I',$out)
 if($Kind -eq 'menu'){
  $sources=@('xq_boot_menu_start.S','xq_boot_menu.c','xq_boot_menu_contract.c') | ForEach-Object {Join-Path $runtime $_}
  $link=Join-Path $runtime 'xq_boot_menu.ld';$stem='xq-boot-menu'
 }else{
  if(-not(Test-Path -LiteralPath (Join-Path $out 'sd_namespace_install.h'))){throw 'Prepare exact CID/source/install header first'}
  $sources=@((Join-Path $repo 'linux/boot/v2_1_sd/source/start.S'),(Join-Path $runtime 'xq_sd_namespace_install.c'))
  $link=Join-Path $out 'sd-namespace-installer.ld'
  $text=(Get-Content -LiteralPath (Join-Path $repo 'linux/boot/v2_1_sd/source/link.ld') -Raw).Replace('ORIGIN = 0x01000000','ORIGIN = 0x01800000')
  [IO.File]::WriteAllText($link,$text,[Text.UTF8Encoding]::new($false));$stem='xq-sd-namespace-install'
  $sources+=@((Join-Path $runtime 'xq_sd_namespace_fat.c'),(Join-Path $boot 'fat_boot_prefix.c'))
 }
 $sources+=Join-Path $runtime 'xq_boot_strings.c'
 foreach($name in @('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c')){$sources+=Join-Path $boot $name}
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out ($stem+'-obj')) -Sources $sources -CompilerArguments $flags
 $elf=Join-Path $out ($stem+'.elf')
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax' "-Wl,-T,$link" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'Namespace tool link failed'}
 $null=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 & $tc.objcopy -O binary $elf (Join-Path $out ($stem+'.bin'))
 if($LASTEXITCODE){throw 'Namespace tool objcopy failed'}
 Write-Output ('SD_NAMESPACE_TOOL_BUILD_PASS kind='+$Kind+' board_validated=false')
}finally{$env:PATH=$saved}
