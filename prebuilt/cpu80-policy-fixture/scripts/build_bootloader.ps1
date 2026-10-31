param([string]$ToolchainRoot='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
. (Join-Path $PSScriptRoot 'release_version.ps1')
. (Join-Path $PSScriptRoot 'compiler_capacity_helpers.ps1')
Write-SocReleaseHeader $root
$cpuOriginalPath = $env:PATH
try {
$toolchain=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$gcc=$toolchain.gcc
$objcopy=$toolchain.objcopy
$objdump=$toolchain.objdump
$size=$toolchain.size
$src=Join-Path $root 'sw\bootloader';$core=Join-Path $root 'sw\coremark';$out=Join-Path $root 'artifacts'
Assert-CpuCoremarkSources -Directory $core
$elf=Join-Path $out 'bootloader.elf';$bin=Join-Path $out 'bootloader.bin';$map=Join-Path $out 'bootloader.map'
$objDir=Join-Path $out 'bootloader_obj'
New-Item -ItemType Directory -Force -Path $objDir | Out-Null
$libgcc=$toolchain.Libgcc
$common=@('-std=gnu99',"-march=$CpuMarch","-mabi=$CpuAbi",'-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-Wall','-Wextra')
$objects=New-Object 'Collections.Generic.List[string]'
$buildCommands=New-Object 'Collections.Generic.List[object]'
$buildInputs=[ordered]@{}
function ConvertTo-ReleaseArgument([string]$Value) {
    return $Value.Replace($toolchain.Root, '@TOOLCHAIN_ROOT@').Replace($root, '@SOC_ROOT@')
}
function Add-BuildCommand([string]$Kind,[string[]]$Arguments) {
    $buildCommands.Add([ordered]@{
        tool='riscv32-unknown-elf-gcc'
        kind=$Kind
        argv=@($Arguments | ForEach-Object { ConvertTo-ReleaseArgument $_ })
    })
}
function Get-TextSha256([string]$Value) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant()
    } finally { $sha.Dispose() }
}
$inputPaths=@('VERSION','config/clocks.json','rtl/cpu/source.json',
    'scripts/build_bootloader.ps1','scripts/riscv_toolchain.ps1',
    'scripts/release_version.ps1','scripts/compiler_capacity_helpers.ps1',
    'sw/bootloader/release_version.h','sw/bootloader/link.ld')
$bootSources=@('start.S','runtime.c','console_line.c','flash.c','net.c','camera.c','camera_sd.c','crc32_fast.c','png_rgb565.c','fat_camera.c','fat_ro.c','sd_native.c','sd_boot.c','audio_sample.c','audio.c','main.c')
foreach($name in $bootSources){
 $source=Join-Path $src $name;$object=Join-Path $objDir (([IO.Path]::GetFileNameWithoutExtension($name))+'.o')
 # The boot BRAM needs a 16 KiB stack reserve with the local GCC 16.2.0.
 # Preserve CoreMark and the camera/CRC/PNG compute paths at -O2; compact
 # the SD camera orchestration and FAT paths at -Os. LTO is bootloader-only.
 $optimization=if($name -in @('camera.c','crc32_fast.c','png_rgb565.c')){'-O2'}else{'-Os'}
 $args=@($common)+@($optimization,'-flto','-Werror','-I',$src,'-c',$source,'-o',$object)
 Add-BuildCommand 'compile_bootloader' $args
 & $gcc @args
 if($LASTEXITCODE){throw "GCC failed for ${name}: $LASTEXITCODE"}
 $objects.Add($object)
 $inputPaths+=('sw/bootloader/'+$name)
}
$coreSources=@('core_main.c','core_list_join.c','core_matrix.c','core_state.c','core_util.c','core_portme.c')
foreach($name in $coreSources){
 $source=Join-Path $core $name;$object=Join-Path $objDir (([IO.Path]::GetFileNameWithoutExtension($name))+'.o')
 $definitions=@('-Dmain=coremark_benchmark_main')
 $coreArgs=$common+@('-O2','-I',$core)+$definitions+@('-c',$source,'-o',$object)
 Add-BuildCommand 'compile_coremark' $coreArgs
 & $gcc @coreArgs
 if($LASTEXITCODE){throw "GCC failed for CoreMark ${name}: $LASTEXITCODE"}
 $objects.Add($object)
 $inputPaths+=('sw/coremark/'+$name)
}
$corePreprocessBase=$common+@('-O2','-I',$core,'-Dmain=coremark_benchmark_main')
$macroArgs=$corePreprocessBase+@('-dM','-E',(Join-Path $core 'core_portme.c'))
Add-BuildCommand 'preprocess_coremark_macros' $macroArgs
$macroLines=@(& $gcc @macroArgs)
if($LASTEXITCODE){throw 'CoreMark macro preprocessing failed'}
$actualMacros=@{}
foreach($line in $macroLines){
 if($line -match '^#define ([A-Z][A-Z0-9_]*)\s+(.+)$'){$actualMacros[$Matches[1]]=$Matches[2]}
}
$clock=Get-Content -LiteralPath (Join-Path $root 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedMacros=[ordered]@{
 TOTAL_DATA_SIZE='2*1000'; ITERATIONS='0'; VALIDATION_RUN='0'
 PERFORMANCE_RUN='(!VALIDATION_RUN)'; PROFILE_RUN='0'
 CORE_CLOCKS_PER_SEC=([string]$clock.timebase_hz+'ULL'); SEED_METHOD='SEED_VOLATILE'
 MULTITHREAD='1'
}
foreach($name in $expectedMacros.Keys){
 if($actualMacros[$name] -cne $expectedMacros[$name]){
  throw "CoreMark preprocessed $name differs from release contract: $($actualMacros[$name])"
 }
}
$portmeArgs=$corePreprocessBase+@('-E','-P',(Join-Path $core 'core_portme.c'))
Add-BuildCommand 'preprocess_coremark_portme' $portmeArgs
$portmeText=(& $gcc @portmeArgs | Out-String)
if($LASTEXITCODE){throw 'CoreMark port preprocessing failed'}
foreach($needle in @(
 'volatile ee_s32 seed1_volatile = 0 ? 0x3415 : 0;',
 'volatile ee_s32 seed2_volatile = 0 ? 0x3415 : 0;',
 'volatile ee_s32 seed3_volatile = 0x66;',
 'seed1_volatile = validation ? 0x3415 : 0;',
 'seed2_volatile = validation ? 0x3415 : 0;',
 'seed3_volatile = 0x66;'
)){
 if(!$portmeText.Contains($needle)){throw "CoreMark preprocessed seed behavior missing: $needle"}
}
$mainArgs=$corePreprocessBase+@('-E','-P',(Join-Path $core 'core_main.c'))
Add-BuildCommand 'preprocess_coremark_main' $mainArgs
$mainText=(& $gcc @mainArgs | Out-String)
if($LASTEXITCODE -or $mainText -notmatch 'static_memblk\[2\s*\*\s*1000\]'){
 throw 'CoreMark preprocessed static workspace is not 2000 bytes'
}
$coremarkContract=[ordered]@{
 source='GCC 16.2.0 -E/-dM with the same common, -O2, include and define arguments as the linked CoreMark objects'
 preprocessed_macros=$expectedMacros
 total_data_size_bytes=2000
 runtime_performance_seed=@(0,0,102)
 runtime_validation_seed=@(13333,13333,102)
 iterations='runtime automatic calibration (ITERATIONS=0)'
 timebase_hz=$clock.timebase_hz
 portme_preprocessed_sha256=(Get-TextSha256 $portmeText)
 main_preprocessed_sha256=(Get-TextSha256 $mainText)
}
$linkArgs=$common+$objects+@('-flto','-nostartfiles','-nostdlib',"-T$(Join-Path $src 'link.ld')",'-Wl,--gc-sections','-Wl,--build-id=none',"-Wl,-Map,$map",$libgcc,'-o',$elf)
Add-BuildCommand 'link' $linkArgs
& $gcc @linkArgs
if($LASTEXITCODE){throw "GCC link failed: $LASTEXITCODE"}
$stackLayout=Get-BootloaderCapacityLayout -Map $map
if (!$stackLayout.stack_gate_passed) { throw 'Production bootloader leaves less than 16 KiB stack' }
$mapLines=[IO.File]::ReadAllLines($map)|ForEach-Object{$_.TrimEnd()}
[IO.File]::WriteAllLines($map,$mapLines,[Text.UTF8Encoding]::new($false))
& $objcopy -O binary $elf $bin
if($LASTEXITCODE){throw "objcopy failed: $LASTEXITCODE"}
if((Get-Item -LiteralPath $bin).Length -gt 131072){throw 'Bootloader exceeds 128 KiB boot BRAM'}
& (Join-Path $PSScriptRoot 'bin_to_hex.ps1') -InputBin $bin -OutputHex (Join-Path $root 'pds\bootrom.hex') -MemoryBytes 131072
Copy-Item -LiteralPath (Join-Path $root 'pds\bootrom.hex') -Destination (Join-Path $out 'bootrom.hex') -Force
$disasm=Join-Path $out 'bootloader.disasm.txt'
(& $objdump -d $elf | Out-String) | Set-Content -LiteralPath $disasm -Encoding utf8
if(Select-String -LiteralPath $disasm -Pattern 'csrr.*mcycle' -Quiet){
    throw 'Production CoreMark and bootloader timing must use the shared CLINT mtime contract'
}
if(!(Select-String -LiteralPath $map -Pattern 'coremark_command' -Quiet)){
    throw 'CoreMark command was removed from the bootloader image'
}
(& $size -A $elf | Out-String) | Set-Content -LiteralPath (Join-Path $out 'bootloader.size.txt') -Encoding utf8
$hashPath=Join-Path $out 'SHA256SUMS.txt'
[string[]]$hash = @(if(Test-Path -LiteralPath $hashPath){
    [IO.File]::ReadAllLines($hashPath) | Where-Object {
        $_ -match '^[0-9a-f]{64}  [A-Za-z0-9_.-]+$' -and
        $_ -notmatch '\s+(bootloader\.elf|bootloader\.bin|bootrom\.hex)$'
    }
})
$hash += @(Get-FileHash -LiteralPath @($elf,$bin,(Join-Path $out 'bootrom.hex')) -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($_.Path))" })
[IO.File]::WriteAllLines($hashPath,$hash,[Text.UTF8Encoding]::new($false))
foreach ($relative in $inputPaths) {
    $buildInputs[$relative] = (Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
    -Optimization 'CoreMark/camera/CRC/PNG -O2; other bootloader code -Os; bootloader LTO' -UsesLibgcc -CoremarkDirectory $core `
    -BuildCommands @($buildCommands.ToArray()) -BuildInputs $buildInputs -StackLayout $stackLayout `
    -CoremarkContract $coremarkContract -CoremarkIterations ([int]$actualMacros['ITERATIONS'])
Write-Host "Bootloader built: $bin"
} finally {
    $env:PATH = $cpuOriginalPath
}
