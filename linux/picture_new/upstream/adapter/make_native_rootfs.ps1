param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$GuiDirectory='build/picture-p21-native/gui-r04',
      [string]$Bundle='build/picture-p21-native/native-r04.tar.gz',
      [string]$CameraHelper='build/picture-p21-native/xq-camera-exec')
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$out=[IO.Path]::GetFullPath((Join-Path $repo $OutputDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if(!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){
 throw 'Choose a fresh output directory strictly under build/.'
}
New-Item -ItemType Directory -Path $out | Out-Null
foreach($name in @('xiangqi-pikafish-gui','xq-camera-capture')){
 Copy-Item -LiteralPath (Join-Path (Join-Path $repo $GuiDirectory) $name) -Destination (Join-Path $out $name)
}
& (Join-Path $repo 'scripts/make_picture_rootfs.ps1') -CandidateDirectory $OutputDirectory
Move-Item -LiteralPath (Join-Path $out 'brfs2.bin') -Destination (Join-Path $out 'base.cpio')
$config=Join-Path $out 'xq-picture-native.conf'
$text=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'runtime/xq-picture-native.conf'))
$text=$text.Replace('/run/xq-native/xq-native-worker-r04','/run/xq-native/xq-native-worker')
[IO.File]::WriteAllText($config,$text,[Text.UTF8Encoding]::new($false))
$payloads=@(
 @{Name='usr/bin/xiangqi-pikafish';Path=(Join-Path $PSScriptRoot 'runtime/xiangqi-model-launcher');Mode=0x81ed},
 @{Name='usr/bin/xq-camera-exec';Path=(Join-Path $repo $CameraHelper);Mode=0x81ed},
 @{Name='etc/xq-picture.conf';Path=$config;Mode=0x81a4},
 @{Name='opt/xq-native/native-models.tar.gz';Path=(Join-Path $repo $Bundle);Mode=0x81a4}
)
& (Join-Path $repo 'scripts/make_rootfs.ps1') -SourcePath (Join-Path $out 'base.cpio') `
 -OutputPath (Join-Path $out 'brfs2.bin') -SkipDtbUpdate -AdditionalPayloads $payloads
if((Get-Item -LiteralPath (Join-Path $out 'brfs2.bin')).Length -gt 0x1000000){throw 'Native rootfs exceeds the frozen 16 MiB raw aperture.'}
$records=@{}
foreach($entry in $payloads){
 $records[$entry.Name]=@{bytes=(Get-Item -LiteralPath $entry.Path).Length;sha256=(Get-FileHash -LiteralPath $entry.Path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$records['brfs2.bin']=@{bytes=(Get-Item -LiteralPath (Join-Path $out 'brfs2.bin')).Length;sha256=(Get-FileHash -LiteralPath (Join-Path $out 'brfs2.bin') -Algorithm SHA256).Hash.ToLowerInvariant()}
$record=@{scope='EXPERIMENTAL native RAM boot candidate; M0 FAIL; not cold-boot board acceptance';files=$records}
[IO.File]::WriteAllText((Join-Path $out 'native-rootfs.json'),($record|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'NATIVE_ROOTFS_BUILD_PASS board_validated=false sd_written=false'
