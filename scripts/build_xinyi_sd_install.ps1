param([Parameter(Mandatory=$true)][string]$CandidateDirectory,[string]$ToolchainRoot='D:/p17-gcc16-lto/native')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath($CandidateDirectory)
if(!$out.StartsWith([IO.Path]::GetFullPath((Join-Path $repo 'build'))+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Private build/ output required'}
if(Test-Path (Join-Path $out 'PN03INST.BIN')){throw 'Never overwrite an installer'}
$support=Join-Path $out 'support';$saved=$env:PATH
try{
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $sources=@();foreach($name in @('start.S','install.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c','install_fat.c','install_xmodem.c')){$sources+=Join-Path $support $name}
 $flags=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-O2','-Wall','-Wextra','-Werror','-I',$support)
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'obj') -Sources $sources -CompilerArguments $flags
 $elf=Join-Path $out 'PN03INST.ELF'
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax,--build-id=none' "-Wl,-T,$support/link.ld" "-Wl,-Map,$out/PN03INST.map" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'Installer link failed'}
 $metadata=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 $code=Assert-CpuCode -Toolchain $tc -Elf $elf
 & $tc.objcopy -O binary $elf (Join-Path $out 'PN03INST.BIN');if($LASTEXITCODE){throw 'Installer objcopy failed'}
 & $tc.objcopy --redefine-sym main=pn03_install_main (Join-Path $out 'obj/01_install.c.o') (Join-Path $out 'rv32-install-test.o')
 if($LASTEXITCODE){throw 'Installer test object alias failed'}
 $symbols=(& $tc.nm -n $elf | Out-String)
 if($symbols -match '(?m)\b(flash_write_image|flash_erase|fat_boot_patch_prefix)\s*$'){throw 'Forbidden writer linked'}
 [IO.File]::WriteAllText((Join-Path $out 'symbols.txt'),$symbols,[Text.UTF8Encoding]::new($false))
 $record=@{status='CPU60_PN03_INSTALLER_COMPILED_NOT_BOARD';compiler_target=$tc.Target;compiler_version=$tc.Version;libgcc_sha256=$tc.LibgccSha256;elf=$metadata;code=$code;entry='0x01800000';sd_written=$false;flash_written=$false}
 [IO.File]::WriteAllText((Join-Path $out 'compile.json'),($record|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host 'CPU60_PN03_INSTALLER_GCC16_PASS_NOT_BOARD'
}finally{$env:PATH=$saved}
