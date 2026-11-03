param(
    [string]$Distro = 'pikafish-verify',
    [string]$BuildDir = 'build/nnue10ms'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (![IO.Path]::IsPathRooted($BuildDir)) { $BuildDir = Join-Path $root $BuildDir }
$BuildDir = [IO.Path]::GetFullPath($BuildDir)
$out = Join-Path $BuildDir 'image'
[IO.Directory]::CreateDirectory($out) | Out-Null
function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') { throw "Not a Windows path: $full" }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\','/')
}
$gui = Join-Path $BuildDir 'pikafish/xiangqi-pikafish-gui'
$payloads = @(
    @{Name='usr/bin/pikafish-nnue-latency'; Path=(Join-Path $BuildDir 'pikafish/pikafish-nnue-latency'); Mode=0x81ed},
    @{Name='usr/bin/pango-mac-resident-test'; Path=(Join-Path $BuildDir 'pango-mac-resident-test'); Mode=0x81ed},
    @{Name='usr/bin/xqvoice'; Path=(Join-Path $BuildDir 'voice/xqvoice'); Mode=0x81ed},
    @{Name='usr/bin/xqvoice-send'; Path=(Join-Path $BuildDir 'voice/xqvoice-send'); Mode=0x81ed},
    @{Name='opt/pikafish/nnue10ms.vectors'; Path=(Join-Path $BuildDir 'nnue10ms.vectors'); Mode=0x81a4},
    @{Name='usr/bin/run-nnue10ms-board'; Path=(Join-Path $root 'linux/pikafish/run_nnue10ms_board.sh'); Mode=0x81ed}
)
foreach ($name in @('pango-mac-conv-window-test','pango-mac-conv-compute-test',
                    'pango-mac-scheduler-test','pango-mac-pool-test')) {
    $payloads += @{Name="usr/bin/$name"; Path=(Join-Path $BuildDir "conv-rootfs/$name"); Mode=0x81ed}
}
$payloadManifest = Join-Path $out 'nnue10ms-payloads.sha256'
$manifestLines = @($payloads + @{Name='usr/bin/xiangqi-pikafish-gui';Path=$gui},
    @{Name='opt/pikafish/stageb-mac.bin';Path=(Join-Path $root 'artifacts/pikafish-stageb-mac.bin')}) | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  /$($_.Name)"
}
[IO.File]::WriteAllText($payloadManifest,($manifestLines -join "`n")+"`n",
    [Text.UTF8Encoding]::new($false))
$payloads += @{Name='opt/pikafish/nnue10ms-payloads.sha256';Path=$payloadManifest;Mode=0x81a4}
$rootfs = Join-Path $out 'rootfs.cpio'
& (Join-Path $PSScriptRoot 'make_rootfs.ps1') `
    -SourcePath (Join-Path $root 'linux/boot/rootfs.cpio') -OutputPath $rootfs `
    -IncludePikafish -ExternalPff1 -SkipDtbUpdate -PikafishGuiPath $gui `
    -PikafishModelPath (Join-Path $root 'linux/boot/pikafish.pff') -AdditionalPayloads $payloads

$dts = Join-Path $out 'cpu_v2.candidate.dts'
$dtb = Join-Path $out 'cpu_v2.dtb'
$text = [IO.File]::ReadAllText((Join-Path $root 'linux/cpu_v2.dts'))
if ([regex]::Matches($text,'linux,initrd-start\s*=\s*<0x03000000>;').Count -ne 1 -or
    [regex]::Matches($text,'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>;').Count -ne 1) {
    throw 'Unexpected source initrd address contract'
}
$end = 0x03000000L + (Get-Item -LiteralPath $rootfs).Length
if ($end -gt 0x08000000) { throw 'Candidate initrd exceeds its 80 MiB slot' }
$text = [regex]::Replace($text,'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>;',
    ('linux,initrd-end = <0x{0:x8}>;' -f $end))
[IO.File]::WriteAllText($dts,$text,[Text.UTF8Encoding]::new($false))
$ErrorActionPreference = 'Continue'
& wsl.exe -d $Distro -u root -- dtc -q -I dts -O dtb -o (Convert-ToWslPath $dtb) (Convert-ToWslPath $dts) 2>$null
$dtcExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($dtcExit -ne 0) { throw 'Candidate DTB compilation failed' }
Copy-Item -LiteralPath (Join-Path $BuildDir 'linux/Image') -Destination (Join-Path $out 'Image')
Copy-Item -LiteralPath (Join-Path $root 'linux/boot/fw_jump.bin') -Destination $out
foreach ($name in @('pikafish.pff','pikafish.atk','mac_selftest.bin')) {
    Copy-Item -LiteralPath (Join-Path $root "linux/boot/$name") -Destination $out
}
& (Join-Path $PSScriptRoot 'test_mac_conv_stage2_initrd_contract.ps1') `
    -RootfsPath $rootfs -DtbPath $dtb -Distro $Distro
& (Join-Path $PSScriptRoot 'test_pikafish_rootfs.ps1') -RootfsPath $rootfs `
    -DtsPath $dts -DtbPath $dtb -GuiPath $gui -AdditionalPayloads $payloads -Distro $Distro
$paths = @('Image','fw_jump.bin','cpu_v2.dtb','rootfs.cpio','pikafish.pff','pikafish.atk',
           'mac_selftest.bin') | ForEach-Object { Join-Path $out $_ }
$paths += @((Join-Path $root 'linux/boot/pikafish.pff'),(Join-Path $root 'linux/boot/pikafish.atk'),
             (Join-Path $BuildDir 'nnue10ms.vectors'),$gui)
$paths += @($payloads | ForEach-Object { $_.Path })
$paths | Sort-Object -Unique | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $_"
} | Set-Content -LiteralPath (Join-Path $out 'sha256sums.txt') -Encoding Ascii
Write-Output "NNUE10MS_IMAGE_PASS directory=$out"
