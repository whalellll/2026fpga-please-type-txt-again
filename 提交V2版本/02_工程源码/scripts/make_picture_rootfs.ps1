param([string]$CandidateDirectory='build/picture-candidate',[switch]$RoiPreview,[string]$SourcePath)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if (!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Picture rootfs must stay under build/.' }
$source=Join-Path $repo 'linux/boot/v2_1_sd/rootfs_payloads/picture'
$gui=Join-Path $out 'xiangqi-pikafish-gui'
$capture=Join-Path $out 'xq-camera-capture'
foreach($file in @($gui,$capture)) {
 if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Build target Linux candidate first: $file" }
 $bytes=[IO.File]::ReadAllBytes($file)
 if ($bytes.Length -lt 52 -or [Text.Encoding]::ASCII.GetString($bytes,1,3) -ne 'ELF' -or
     $bytes[0] -ne 127 -or $bytes[4] -ne 1 -or $bytes[5] -ne 1 -or
     [BitConverter]::ToUInt16($bytes,18) -ne 243 -or [BitConverter]::ToUInt32($bytes,36) -ne 0) {
  throw "Expected ELF32 RISC-V soft-float/no-C binary: $file"
 }
}
$payloads=@(
 @{Name='usr/bin/xiangqi-pikafish-gui';Path=$gui;Mode=0x81ed},
 @{Name='usr/bin/xq-camera-capture';Path=$capture;Mode=0x81ed},
 @{Name='usr/bin/xiangqi-pikafish';Path=(Join-Path $source 'xiangqi-pikafish');Mode=0x81ed},
 @{Name='etc/xq-picture.conf';Path=(Join-Path $source 'xq-picture.conf');Mode=0x81a4},
 @{Name='opt/xq-picture/opening.stub';Path=(Join-Path $source 'opening.stub');Mode=0x81a4}
)
if($RoiPreview){
 $config=Join-Path $out 'xq-picture-roi-preview.conf'
 $text=[IO.File]::ReadAllText((Join-Path $source 'xq-picture.conf')).Replace('XQ_PICTURE_MODE=stub','XQ_PICTURE_MODE=roi-preview')
 $text+="`nexport PIKAFISH_MAC_BACKEND=driver`nexport PIKAFISH_MAC_REQUIRE_DRIVER=1`nexport PIKAFISH_MAC_REQUIRE_FEATURES=0x60`n"
 [IO.File]::WriteAllText($config,$text,[Text.UTF8Encoding]::new($false))
 $payloads | Where-Object {$_.Name -eq 'etc/xq-picture.conf'} | ForEach-Object {$_.Path=$config}
}
$pcm=Join-Path $source 'pcm'
$speechManifest=Get-Content -Encoding UTF8 -LiteralPath (Join-Path $pcm 'manifest.json') -Raw | ConvertFrom-Json
if ($speechManifest.contract_version -ne 1 -or $speechManifest.format -ne 's16le' -or
    $speechManifest.sample_rate -ne 16000 -or $speechManifest.channels -ne 1) { throw 'Invalid Picture PCM contract.' }
foreach($entry in $speechManifest.files.PSObject.Properties) {
 if ($entry.Name -notmatch '^[a-z_]+\.pcm$') { throw 'Invalid PCM filename.' }
 $path=Join-Path $pcm $entry.Name
 $file=Get-Item -LiteralPath $path
 if ($file.Length -ne $entry.Value.bytes -or $file.Length%2 -or
     (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) {
  throw "Picture PCM contract mismatch: $($entry.Name)"
 }
 $payloads+=@{Name=('opt/xq-picture/pcm/'+$entry.Name);Path=$path;Mode=0x81a4}
}
$payloads+=@{Name='opt/xq-picture/pcm/manifest.json';Path=(Join-Path $pcm 'manifest.json');Mode=0x81a4}
if(!$SourcePath){$SourcePath=Join-Path $repo 'linux/boot/rootfs.cpio'}
& (Join-Path $PSScriptRoot 'make_rootfs.ps1') -SourcePath $SourcePath `
 -OutputPath (Join-Path $out 'brfs2.bin') -SkipDtbUpdate -AdditionalPayloads $payloads
if($LASTEXITCODE) { throw 'Picture rootfs build failed' }
if ((Get-Item -LiteralPath (Join-Path $out 'brfs2.bin')).Length -gt 0x01000000) {
 throw 'Picture rootfs exceeds the frozen RAM loader 16 MiB aperture.'
}
if($RoiPreview){Write-Output 'PICTURE_ROOTFS_CANDIDATE_PASS backend=roi-preview no_model=true board_validated=false'}
else{Write-Output 'PICTURE_ROOTFS_CANDIDATE_PASS backend=stub board_validated=false'}
