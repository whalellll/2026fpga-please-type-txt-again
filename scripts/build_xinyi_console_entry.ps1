param([Parameter(Mandatory=$true)][string]$CandidateDirectory,[string]$ToolchainRoot='D:/p17-gcc16-lto/native')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath($CandidateDirectory)
if(!$out.StartsWith([IO.Path]::GetFullPath((Join-Path $repo 'build'))+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Private build/ output required'}
if(Test-Path (Join-Path $out 'entry-installer.bin')){throw 'Preserve prior binaries'}
$contract=Get-Content (Join-Path $out 'entry_contract.json') -Raw -Encoding UTF8|ConvertFrom-Json
foreach($input in $contract.source_inputs.PSObject.Properties){
 if((Get-FileHash -LiteralPath $input.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $input.Value.sha256){throw 'Stale entry source'}
}
$saved=$env:PATH
try{
 $tc=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
 $support=Join-Path $out 'support';$sources=@()
 foreach($name in @('start.S','install_sd_console.c','fat_camera.c','fat_boot_prefix.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c')){$sources+=Join-Path $support $name}
 $flags=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-O2','-Wall','-Wextra','-Werror','-I',$support)
 $objects=Build-CpuObjects -Toolchain $tc -Directory (Join-Path $out 'obj') -Sources $sources -CompilerArguments $flags
 $elf=Join-Path $out 'entry-installer.elf'
 & $tc.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -static '-Wl,--gc-sections,--no-relax,--build-id=none' "-Wl,-T,$support/link.ld" @objects $tc.Libgcc -o $elf
 if($LASTEXITCODE){throw 'Entry installer link failed'}
 $metadata=Assert-CpuElf -Readelf $tc.readelf -Path $elf
 $code=Assert-CpuCode -Toolchain $tc -Elf $elf
 & $tc.objcopy -O binary $elf (Join-Path $out 'entry-installer.bin')
 if($LASTEXITCODE){throw 'Entry installer objcopy failed'}
 $symbols=(& $tc.nm -n $elf|Out-String)
 if($symbols -match '(?m)\b(flash_write_image|flash_erase)\s*$' -or $symbols -notmatch '\bfat_boot_patch_prefix\b'){throw 'Entry writer symbol audit failed'}
 [IO.File]::WriteAllText((Join-Path $out 'symbols.txt'),$symbols,[Text.UTF8Encoding]::new($false))
 $record=@{status='COMPILED_NOT_INSTALLED';elf=$metadata;code=$code;compiler_version=$tc.Version;libgcc_sha256=$tc.LibgccSha256;installer_sha256=(Get-FileHash (Join-Path $out 'entry-installer.bin') -Algorithm SHA256).Hash.ToLowerInvariant();sd_written=$false;flash_written=$false}
 [IO.File]::WriteAllText((Join-Path $out 'compile.json'),($record|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host 'EXACT_CARD_ENTRY_INSTALLER_GCC16_COMPILE_PASS_NOT_BOARD'
}finally{$env:PATH=$saved}
