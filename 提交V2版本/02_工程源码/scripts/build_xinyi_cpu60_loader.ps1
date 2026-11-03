param([Parameter(Mandatory=$true)][string]$CandidateDirectory,
      [string]$ToolchainRoot='D:/p17-gcc16-lto/native',
      [ValidateSet('PN03','PN04')][string]$Prefix='PN03')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$out=[IO.Path]::GetFullPath($CandidateDirectory)
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if(!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Use private build/ output'}
$support=Join-Path $out 'support'
foreach($name in @('loader.c','link.ld','start.S','payloads.h','target.h','boot/soc.h')){
 if(!(Test-Path -LiteralPath (Join-Path $support $name) -PathType Leaf)){throw "Missing prepared input: $name"}
}
if(Test-Path -LiteralPath (Join-Path $out ($Prefix+'BOOT.BIN'))){throw 'Never overwrite an existing loader'}
$saved=$env:PATH
try{
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $boot=Join-Path $support 'boot'
 $sources=@((Join-Path $support 'start.S'),(Join-Path $support 'loader.c'))
 foreach($name in @('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c')){$sources+=Join-Path $boot $name}
 $sources+=Join-Path $support 'xq_camera.c'
 $flags=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
 '-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-O2',
 '-Wall','-Wextra','-Werror','-I',$boot,'-I',$support)
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'obj') -Sources $sources -CompilerArguments $flags
 $elf=Join-Path $out ($Prefix+'BOOT.ELF')
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax,--build-id=none' `
  "-Wl,-T,$support/link.ld" "-Wl,-Map,$out/${Prefix}BOOT.map" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'PN03 link failed'}
 $elfMetadata=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 $codeMetadata=Assert-CpuCode -Toolchain $tc -Elf $elf
 & $tc.objcopy -O binary $elf (Join-Path $out ($Prefix+'BOOT.BIN'))
 if($LASTEXITCODE){throw 'PN03 objcopy failed'}
 & $tc.objcopy --redefine-sym main=xinyi_boot_main (Join-Path $out 'obj/01_loader.c.o') (Join-Path $out 'rv32-loader-test.o')
 if($LASTEXITCODE){throw 'PN03 target-object test alias failed'}
 $elfText=(& $tc.readelf -h -A -l $elf | Out-String)
 [IO.File]::WriteAllText((Join-Path $out 'elf.txt'),$elfText,[Text.UTF8Encoding]::new($false))
 $symbols=(& $tc.nm -n $elf | Out-String)
 if($symbols -match '(?m)\b(sd_write_sector|sd_write_sectors|flash_write_image|fat_camera_save)\s*$'){throw 'A media/Flash writer survived into PN03'}
 [IO.File]::WriteAllText((Join-Path $out 'symbols.txt'),$symbols,[Text.UTF8Encoding]::new($false))
 $record=[ordered]@{status=('CPU60_PRIVATE_'+$Prefix+'_COMPILE_PASS_NOT_BOARD');compiler_target=$tc.Target;compiler_version=$tc.Version;
  compiler_sha256=(Get-FileHash -LiteralPath $tc.gcc -Algorithm SHA256).Hash.ToLowerInvariant();
  toolchain_root=$tc.Root;libgcc=$tc.Libgcc;libgcc_sha256=$tc.LibgccSha256;libgcc_metadata=$tc.LibgccMetadata;
  flags=$flags;sources=$sources;elf_metadata=$elfMetadata;code_validation=$codeMetadata;entry='0x01000000';
  board_validated=$false;sd_written=$false;flash_written=$false;rom_rebuilt=$false}
 [IO.File]::WriteAllText((Join-Path $out 'compile.json'),($record|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
 Write-Output ('XINYI_CPU60_'+$Prefix+'_LOADER_GCC16_BUILD_PASS_NOT_BOARD')
}finally{$env:PATH=$saved}
