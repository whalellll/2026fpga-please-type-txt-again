param([string]$ToolchainRoot='', [Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$SdReceipt)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if(!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Use ignored build/ output'}
$receipt=Get-Content -LiteralPath $SdReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if($receipt.status -ne 'PASS' -or !$receipt.boot_from_sd -or $receipt.cid -notmatch '^[a-f0-9]{32}$'){throw 'Require the verified SD deployment receipt'}
$contract=Get-Content -LiteralPath (Join-Path $out 'sd_contract.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$prefix=[string]$contract.deployment.prefix
if($prefix -notmatch '^[A-Z][A-Z0-9]{1,2}$'){throw 'Invalid candidate FAT prefix'}
$backupStem=$prefix+'XOLD';$loaderStem=$prefix+'XBOOT'
& (Join-Path $PSScriptRoot 'build_picture_loader.ps1') -ToolchainRoot $ToolchainRoot -CandidateDirectory $CandidateDirectory
if($LASTEXITCODE){throw 'SD Linux loader failed'}
$bytes=[IO.File]::ReadAllBytes((Join-Path $out 'loader-picture-candidate.bin'))
if($bytes.Length -gt 32768 -or $bytes.Length%4){throw 'SD prefix must be aligned and fit the first cluster'}
$header=New-Object Text.StringBuilder
[void]$header.AppendLine('/* Exact verified card and Linux loader at 0x01000000. */')
[void]$header.AppendLine('#define CONSOLE_BACKUP_NAME "'+$backupStem+'.BIN"')
[void]$header.AppendLine('#define CONSOLE_LOADER_NAME "'+$loaderStem+'.BIN"')
[void]$header.AppendLine('#define CONSOLE_BACKUP_SHORT "'+$backupStem.PadRight(8)+'BIN"')
[void]$header.AppendLine('#define CONSOLE_LOADER_SHORT "'+$loaderStem.PadRight(8)+'BIN"')
$cid=@();for($i=0;$i -lt 4;$i++){$cid+=('0x'+$receipt.cid.Substring($i*8,8)+'u')}
[void]$header.AppendLine('#define CONSOLE_CARD_CID {'+($cid -join ',')+'}')
[void]$header.AppendLine('#define CONSOLE_BOOT_BYTES '+$bytes.Length+'u')
[void]$header.AppendLine('static const uint32_t console_boot[] = {')
for($i=0;$i -lt $bytes.Length;$i+=4){
 [void]$header.Append(('0x{0:x8}u,' -f [BitConverter]::ToUInt32($bytes,$i)))
 if($i%32 -eq 28){[void]$header.AppendLine()}
}
[void]$header.AppendLine('};')
$model=[IO.File]::ReadAllBytes((Join-Path $repo 'linux/boot/xqmodel.bin'))
if($model.Length -ne 207792){throw 'Unexpected fixed ROM-carrier model size'}
[void]$header.AppendLine('static const uint32_t console_model[] = {')
for($i=0;$i -lt $model.Length;$i+=4){
 [void]$header.Append(('0x{0:x8}u,' -f [BitConverter]::ToUInt32($model,$i)))
 if($i%32 -eq 28){[void]$header.AppendLine()}
}
[void]$header.AppendLine('};')
[IO.File]::WriteAllText((Join-Path $out 'picture_console_boot.h'),$header.ToString(),(New-Object Text.UTF8Encoding($false)))
$saved=$env:PATH
try{
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $src=Join-Path $repo 'sw/bootloader';$loader=Join-Path $repo 'linux/boot/v2_1_sd/source'
 $privateFat=Join-Path $loader 'picture_fat_write'
 $link=Join-Path $out 'console-installer.ld'
 [IO.File]::WriteAllText($link,(Get-Content (Join-Path $loader 'link.ld') -Raw).Replace('ORIGIN = 0x01000000','ORIGIN = 0x01800000'),(New-Object Text.UTF8Encoding($false)))
 $args=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
 '-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections',
 '-O2','-Wall','-Wextra','-Werror','-I',$privateFat,'-I',$src,'-I',$out)
 $sources=@((Join-Path $loader 'start.S'),(Join-Path $loader 'install_sd_console.c'))
 foreach($name in @('fat_camera.c','fat_boot_prefix.c')){$sources+=Join-Path $privateFat $name}
 foreach($name in @('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c')){$sources+=Join-Path $src $name}
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'console-installer-obj') -Sources $sources -CompilerArguments $args
 $elf=Join-Path $out 'install-sd-console.elf'
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax' "-Wl,-T,$link" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'SD console installer link failed'}
 $null=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 & $tc.objcopy -O binary $elf (Join-Path $out 'install-sd-console.bin')
 if($LASTEXITCODE){throw 'SD console installer objcopy failed'}
 Write-Output 'PICTURE_SD_CONSOLE_BOOT_BUILD_PASS board_validated=false'
}finally{$env:PATH=$saved}
