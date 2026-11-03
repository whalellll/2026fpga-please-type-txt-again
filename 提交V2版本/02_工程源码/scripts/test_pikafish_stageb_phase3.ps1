param(
    [string]$Pff1Path,
    [string]$PfsbPath,
    [string]$GoldenPath,
    [string]$VerifierPath,
    [string]$GuiPath,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$Pff1Path) { $Pff1Path = Join-Path $root 'linux\boot\pikafish.pff' }
if (!$PfsbPath) { $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin' }
if (!$GoldenPath) {
    $GoldenPath = Join-Path $root 'artifacts\pikafish-stageb-position-golden.bin'
}
if (!$VerifierPath) {
    $VerifierPath = Join-Path $root 'artifacts\pikafish-stageb-position-view-x86_64'
}
if (!$GuiPath) { $GuiPath = Join-Path $root 'artifacts\xiangqi-pikafish-gui' }

foreach ($path in @($Pff1Path, $PfsbPath, $GoldenPath, $VerifierPath, $GuiPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-3 input: $path"
    }
}

function Assert-Contains([string]$Text, [string]$Needle, [string]$Contract) {
    if (!$Text.Contains($Needle)) {
        throw "Stage B phase-3 $Contract contract missing: $Needle"
    }
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

function Get-Crc32([byte[]]$Bytes, [int]$Offset, [int]$Count) {
    [uint32]$crc = [uint32]::MaxValue
    [uint32]$polynomial = 3988292384
    for ($index = $Offset; $index -lt $Offset + $Count; ++$index) {
        $crc = [uint32]($crc -bxor $Bytes[$index])
        for ($bit = 0; $bit -lt 8; ++$bit) {
            [uint32]$mask = if (($crc -band 1) -ne 0) { $polynomial } else { 0 }
            $crc = [uint32](($crc -shr 1) -bxor $mask)
        }
    }
    return [uint32]($crc -bxor [uint32]::MaxValue)
}

function Set-Le32([byte[]]$Bytes, [int]$Offset, [uint32]$Value) {
    $Bytes[$Offset] = [byte]($Value -band 0xff)
    $Bytes[$Offset + 1] = [byte](($Value -shr 8) -band 0xff)
    $Bytes[$Offset + 2] = [byte](($Value -shr 16) -band 0xff)
    $Bytes[$Offset + 3] = [byte](($Value -shr 24) -band 0xff)
}

$networkPatch = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish-stageb.patch'))
$flatLoader = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish_flat_nnue.inc'))
$stageA = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish_stagea_accel.cpp'))
$stageB = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish_stageb_accel.cpp'))
$runtime = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish_mac_runtime.cpp'))
$runtimeHeader = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\pikafish_mac_runtime.h'))
$buildDriver = [IO.File]::ReadAllText(
    (Join-Path $root 'linux\pikafish\build_in_wsl.sh'))

foreach ($needle in @(
    'network[bucket].propagate(transformedFeatures, nnzInfo, bucket)',
    'stageBHandled = StageBAccel::fc0(bucket, transformedFeatures, buffer.fc_0_out)',
    'StageBAccel::verify(bucket, buffer.fc_0_out, buffer.fc_0_cpu)',
    'buffer.fc_0_out[lane] = buffer.fc_0_cpu[lane]',
    'fc_0.propagate(transformedFeatures, buffer.fc_0_out, nnzInfo)')) {
    Assert-Contains $networkPatch $needle 'official-search-path'
}
Assert-Contains $flatLoader 'StageBAccel::prepare(stageBBinding);' 'engine-lifecycle'
Assert-Contains $flatLoader 'stageBBinding.mlpsCrc32 = sections[5].crc32;' 'model-binding'
Assert-Contains $buildDriver '-DPIKAFISH_STAGEB_ACCEL' 'target-build'
foreach ($needle in @('MacRuntime::Session', 'PIKAFISH_STAGEB_ACCEL_READY',
                      'PIKAFISH_STAGEB_ACCEL_ACTIVE', 'shadow-mismatch')) {
    Assert-Contains $stageB $needle 'stageb-backend'
}
if ($stageA.Contains('/dev/mem') -or $stageB.Contains('/dev/mem')) {
    throw 'Stage A/B still own private /dev/mem mappings instead of the shared runtime'
}
foreach ($needle in @('std::mutex', 'PIKAFISH_MAC_RUNTIME_FUSED',
                      'StageBModelBytes', 'StageAInputOffset')) {
    Assert-Contains ($runtime + $runtimeHeader) $needle 'shared-runtime'
}

$gui = Convert-ToWslPath $GuiPath
$markerCommand = @"
set -eu
strings '$gui' | grep -q 'PIKAFISH_STAGEB_ACCEL_READY'
strings '$gui' | grep -q 'PIKAFISH_STAGEB_ACCEL_ACTIVE'
strings '$gui' | grep -q 'PIKAFISH_STAGEB_ACCEL_MISMATCH'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $markerCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Stage B phase-3 markers are missing from the RV32 GUI image'
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) `
    ('pikafish-stageb-phase3-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    [byte[]]$original = [IO.File]::ReadAllBytes($PfsbPath)
    $truncatedPath = Join-Path $tempRoot 'truncated.bin'
    $payloadPath = Join-Path $tempRoot 'bad-payload.bin'
    $bucketPath = Join-Path $tempRoot 'bad-bucket.bin'
    $modelPath = Join-Path $tempRoot 'bad-model.bin'

    [byte[]]$truncated = New-Object byte[] ($original.Length - 1)
    [Array]::Copy($original, $truncated, $truncated.Length)
    [IO.File]::WriteAllBytes($truncatedPath, $truncated)

    [byte[]]$badPayload = $original.Clone()
    $badPayload[$badPayload.Length - 1] = $badPayload[$badPayload.Length - 1] -bxor 1
    [IO.File]::WriteAllBytes($payloadPath, $badPayload)

    [byte[]]$badBucket = $original.Clone()
    $badBucket[0x1004] = 1
    Set-Le32 $badBucket 0x2c (Get-Crc32 $badBucket 0x1000 ($badBucket.Length - 0x1000))
    Set-Le32 $badBucket 0x78 (Get-Crc32 $badBucket 0 0x78)
    [IO.File]::WriteAllBytes($bucketPath, $badBucket)

    [byte[]]$badModel = $original.Clone()
    $badModel[0x50] = $badModel[0x50] -bxor 1
    Set-Le32 $badModel 0x78 (Get-Crc32 $badModel 0 0x78)
    [IO.File]::WriteAllBytes($modelPath, $badModel)

    $verifier = Convert-ToWslPath $VerifierPath
    $pff1 = Convert-ToWslPath $Pff1Path
    $pfsb = Convert-ToWslPath $PfsbPath
    $golden = Convert-ToWslPath $GoldenPath
    $positiveLog = Convert-ToWslPath (Join-Path $tempRoot 'positive.log')
    $cases = @(
        @{ Path = $truncatedPath; Reason = 'pfsb-contract-size' },
        @{ Path = $payloadPath; Reason = 'pfsb-contract-payload-crc' },
        @{ Path = $bucketPath; Reason = 'pfsb-stack-contract-0' },
        @{ Path = $modelPath; Reason = 'pfsb-contract-decoded-sha' }
    )
    $command = @"
set -eu
'$verifier' --verify '$pff1' '$pff1' '$pfsb' '$golden' >'$positiveLog'
grep -q '^PIKAFISH_STAGEB_PHASE2_HOST_PASS buckets=16 cases=32 ' '$positiveLog'
"@.Replace("`r`n", "`n")
    & wsl.exe -d $Distro -- bash -lc $command
    if ($LASTEXITCODE -ne 0) { throw 'Stage B phase-3 positive binding test failed' }

    foreach ($case in $cases) {
        $bad = Convert-ToWslPath $case.Path
        $negative = Convert-ToWslPath (Join-Path $tempRoot ($case.Reason + '.log'))
        $reason = $case.Reason
        $command = @"
set -eu
if '$verifier' --verify '$pff1' '$pff1' '$bad' '$golden' >'$negative' 2>&1; then
  echo 'invalid PFSB unexpectedly passed: $reason' >&2
  exit 1
fi
grep -q '^PIKAFISH_STAGEB_PHASE2_FAIL reason=$reason' '$negative'
"@.Replace("`r`n", "`n")
        & wsl.exe -d $Distro -- bash -lc $command
        if ($LASTEXITCODE -ne 0) {
            throw "Stage B phase-3 negative binding test failed: $reason"
        }
        Write-Output "PIKAFISH_STAGEB_PHASE3_NEGATIVE_PASS reason=$reason"
    }
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

$pfsbHash = (Get-FileHash -LiteralPath $PfsbPath -Algorithm SHA256).Hash.ToLowerInvariant()
$guiHash = (Get-FileHash -LiteralPath $GuiPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PIKAFISH_STAGEB_PHASE3_HOST_PASS pfsb_sha256=$pfsbHash gui_sha256=$guiHash"
