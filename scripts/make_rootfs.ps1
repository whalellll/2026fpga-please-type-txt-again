param(
    [string]$SourcePath,
    [string]$OutputPath,
    [switch]$IncludePikafish,
    [switch]$IncludeMacSchedulerTest,
    [switch]$EmbeddedOnly = $true,
    [string]$PikafishPath,
    [string]$PikafishGuiPath,
    [string]$PikafishModelPath,
    [string]$StageBPackPath,
    [string]$StageBLoaderPath,
    [string]$StageBGoldenPath,
    [string]$StageBBoardAcceptPath,
    [string]$StageBPositionGoldenPath,
    [string]$StageBPositionAcceptPath,
    [string]$MacSchedulerTestPath,
    [string]$Distro = 'chiplab_sim',
    [switch]$ExternalPff1,
    [switch]$SkipDtbUpdate,
    [hashtable[]]$AdditionalPayloads = @()
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root
if (!$SourcePath) {
    $SourcePath = Join-Path $root 'linux\images\prebuilt_2022_03_23\rootfs.cpio'
}
if (!$OutputPath) {
    $OutputPath = Join-Path $root 'linux\boot\rootfs.cpio'
}
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$overlayRoot = Join-Path $root 'linux\rootfs_overlay'
$modelHash = 'de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
$rootfsLimit = 0x05000000L

if (!(Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "Missing baseline rootfs: $SourcePath"
}
if (!(Test-Path -LiteralPath $overlayRoot -PathType Container)) {
    throw "Missing rootfs overlay: $overlayRoot"
}

$payloads = @()
if ($IncludePikafish) {
    if (!$EmbeddedOnly) {
        if (!$PikafishPath) {
            $PikafishPath = Join-Path $root 'artifacts\pikafish-rv32'
        }
    }
    if (!$PikafishGuiPath) {
        $PikafishGuiPath = Join-Path $root 'artifacts\xiangqi-pikafish-gui'
    }
    if (!$PikafishModelPath) {
        $PikafishModelPath = Join-Path $root 'artifacts\pikafish.nnue.flat'
    }
    if (!$StageBPackPath) {
        $StageBPackPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
    }
    if (!$StageBLoaderPath) {
        $StageBLoaderPath = Join-Path $root 'artifacts\pikafish-stageb-load'
    }
    if (!$StageBGoldenPath) {
        $StageBGoldenPath = Join-Path $root 'artifacts\pikafish-stageb-golden.bin'
    }
    if (!$StageBBoardAcceptPath) {
        $StageBBoardAcceptPath = Join-Path $root 'artifacts\pikafish-stageb-board-accept'
    }
    if (!$StageBPositionGoldenPath) {
        $StageBPositionGoldenPath = Join-Path $root 'artifacts\pikafish-stageb-position-golden.bin'
    }
    if (!$StageBPositionAcceptPath) {
        $StageBPositionAcceptPath = Join-Path $root 'artifacts\pikafish-stageb-position-accept'
    }
    $requiredPayloads = @($PikafishGuiPath, $PikafishModelPath,
        $StageBPackPath, $StageBLoaderPath, $StageBGoldenPath,
        $StageBBoardAcceptPath, $StageBPositionGoldenPath,
        $StageBPositionAcceptPath)
    if (!$EmbeddedOnly) {
        $requiredPayloads += $PikafishPath
    }
    foreach ($path in $requiredPayloads) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing Pikafish payload: $path"
        }
    }
    $actualModelHash = (Get-FileHash -LiteralPath $PikafishModelPath `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualModelHash -ne $modelHash) {
        throw "Pikafish model SHA-256 mismatch: $actualModelHash"
    }
    $modelStream = [IO.File]::OpenRead($PikafishModelPath)
    try {
        [byte[]]$modelMagic = New-Object byte[] 4
        if ($modelStream.Read($modelMagic, 0, 4) -ne 4 -or
            [Text.Encoding]::ASCII.GetString($modelMagic) -ne 'PFF1') {
            throw "Pikafish runtime model is not a PFF1 image: $PikafishModelPath"
        }
    } finally {
        $modelStream.Dispose()
    }
    $payloads = @(
        @{ Name = 'usr/bin/xiangqi-pikafish-gui'; Path = $PikafishGuiPath; Mode = 0x81ed },
        @{ Name = 'usr/bin/pikafish-stageb-load'; Path = $StageBLoaderPath; Mode = 0x81ed },
        @{ Name = 'usr/bin/pikafish-stageb-board-accept'; Path = $StageBBoardAcceptPath; Mode = 0x81ed },
        @{ Name = 'usr/bin/pikafish-stageb-position-accept'; Path = $StageBPositionAcceptPath; Mode = 0x81ed },
        @{ Name = 'opt/pikafish/stageb-mac.bin'; Path = $StageBPackPath; Mode = 0x81a4 },
        @{ Name = 'opt/pikafish/stageb-golden.bin'; Path = $StageBGoldenPath; Mode = 0x81a4 },
        @{ Name = 'opt/pikafish/stageb-position-golden.bin'; Path = $StageBPositionGoldenPath; Mode = 0x81a4 }
    )
    if ($ExternalPff1) {
        $externalModelPath = Join-Path $root 'linux\boot\pikafish.pff'
        if (![IO.Path]::GetFullPath($PikafishModelPath).Equals(
                [IO.Path]::GetFullPath($externalModelPath),
                [StringComparison]::OrdinalIgnoreCase)) {
            Copy-Item -LiteralPath $PikafishModelPath -Destination $externalModelPath -Force
        }
    } else {
        $payloads += @{
            Name = 'opt/pikafish/pikafish.nnue'
            Path = $PikafishModelPath
            Mode = 0x81a4
        }
    }
    if (!$EmbeddedOnly) {
        $payloads = @(
            @{ Name = 'usr/bin/pikafish'; Path = $PikafishPath; Mode = 0x81ed }
        ) + $payloads
    }
}

if ($IncludeMacSchedulerTest) {
    if (!$MacSchedulerTestPath) {
        $MacSchedulerTestPath = Join-Path $root `
            'build\linux-mac-scheduler\out\pango-mac-scheduler-test'
    }
    if (!(Test-Path -LiteralPath $MacSchedulerTestPath -PathType Leaf)) {
        throw "Missing MAC scheduler test: $MacSchedulerTestPath"
    }
    $payloads += @{
        Name = 'usr/bin/pango-mac-scheduler-test'
        Path = $MacSchedulerTestPath
        Mode = 0x81ed
    }
}

foreach ($payload in $AdditionalPayloads) {
    if (!$payload.Name -or $payload.Name.StartsWith('/') -or
        $payload.Name.Contains('..') -or $payload.Name.Contains('\') -or
        !(Test-Path -LiteralPath $payload.Path -PathType Leaf)) {
        throw 'Invalid additional initrd payload'
    }
    $payloads += $payload
}

function Read-HexField([byte[]]$Bytes, [int]$Offset) {
    $text = [Text.Encoding]::ASCII.GetString($Bytes, $Offset, 8)
    return [Convert]::ToUInt32($text, 16)
}

function Get-Aligned4([int64]$Value) {
    return ($Value + 3) -band (-bnot 3)
}

function Write-ZeroPadding([IO.Stream]$Stream, [int64]$Count) {
    if ($Count -le 0) { return }
    $zeros = New-Object byte[] ([int]$Count)
    $Stream.Write($zeros, 0, $zeros.Length)
}

function Test-RootfsTextEntry([string]$Name) {
    return $Name -eq 'etc/inittab' -or $Name -eq 'etc/profile' -or
        $Name.StartsWith('etc/init.d/') -or
        $Name -eq 'usr/bin/xiangqi-pikafish'
}

function Write-NewcEntry(
    [IO.Stream]$Stream,
    [string]$Name,
    [uint32]$Mode,
    [uint32]$Inode,
    [string]$DataPath
) {
    [int64]$fileSize = 0
    [byte[]]$normalizedBytes = $null
    if ($DataPath) {
        if (Test-RootfsTextEntry $Name) {
            [byte[]]$rawBytes = [IO.File]::ReadAllBytes($DataPath)
            $text = [Text.Encoding]::UTF8.GetString($rawBytes)
            $text = $text.Replace("`r`n", "`n").Replace("`r", "`n")
            $normalizedBytes = [Text.UTF8Encoding]::new($false).GetBytes($text)
            $fileSize = $normalizedBytes.LongLength
        } else {
            $fileSize = (Get-Item -LiteralPath $DataPath).Length
        }
    }
    if ($fileSize -gt [uint32]::MaxValue) {
        throw "newc payload is too large: $DataPath"
    }
    $nameBytes = [Text.Encoding]::ASCII.GetBytes($Name)
    $nameSize = $nameBytes.Length + 1
    $nlink = if (($Mode -band 0xf000) -eq 0x4000) { 2 } else { 1 }
    [uint32[]]$fields = @(
        $Inode, $Mode, 0, 0, $nlink, 0, [uint32]$fileSize,
        0, 0, 0, 0, [uint32]$nameSize, 0
    )
    $headerText = '070701' + (($fields | ForEach-Object {
        $_.ToString('x8')
    }) -join '')
    if ($headerText.Length -ne 110) {
        throw "Internal newc header error for $Name"
    }
    $header = [Text.Encoding]::ASCII.GetBytes($headerText)
    $Stream.Write($header, 0, $header.Length)
    $Stream.Write($nameBytes, 0, $nameBytes.Length)
    $Stream.WriteByte(0)
    Write-ZeroPadding $Stream ((Get-Aligned4 $Stream.Position) - $Stream.Position)
    if ($DataPath) {
        if ($null -ne $normalizedBytes) {
            $Stream.Write($normalizedBytes, 0, $normalizedBytes.Length)
        } else {
            $source = [IO.File]::OpenRead($DataPath)
            try {
                $source.CopyTo($Stream)
            } finally {
                $source.Dispose()
            }
        }
    }
    Write-ZeroPadding $Stream ((Get-Aligned4 $Stream.Position) - $Stream.Position)
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $tail = $Matches[2].Replace('\', '/')
    return "/mnt/$drive/$tail"
}

$payloadByName = @{}
foreach ($payload in $payloads) {
    $payloadByName[$payload.Name] = $payload
}

$inputBytes = [IO.File]::ReadAllBytes($SourcePath)
$output = New-Object IO.MemoryStream
$offset = 0
$foundTrailer = $false
$maxInode = [uint32]0
$seen = New-Object 'Collections.Generic.HashSet[string]'
$replaced = New-Object 'Collections.Generic.HashSet[string]'

while ($offset + 110 -le $inputBytes.Length) {
    $magic = [Text.Encoding]::ASCII.GetString($inputBytes, $offset, 6)
    if ($magic -ne '070701' -and $magic -ne '070702') {
        throw "Invalid newc header at offset $offset (magic $magic)"
    }

    $inode = Read-HexField $inputBytes ($offset + 6)
    if ($inode -gt $maxInode) { $maxInode = $inode }
    $fileSize = [int64](Read-HexField $inputBytes ($offset + 54))
    $nameSize = [int](Read-HexField $inputBytes ($offset + 94))
    if ($nameSize -lt 1) { throw "Invalid newc name size at offset $offset" }

    $nameStart = $offset + 110
    $name = [Text.Encoding]::ASCII.GetString($inputBytes, $nameStart,
        $nameSize - 1)
    $dataStart = Get-Aligned4 ($nameStart + $nameSize)
    $nextOffset = Get-Aligned4 ($dataStart + $fileSize)
    if ($nextOffset -gt $inputBytes.Length) {
        throw "Truncated newc entry: $name"
    }
    if ($name -eq 'TRAILER!!!') {
        $foundTrailer = $true
        break
    }

    [void]$seen.Add($name)
    $replacementPath = $null
    if ($payloadByName.ContainsKey($name)) {
        $replacementPath = $payloadByName[$name].Path
    } else {
        $overlayPath = Join-Path $overlayRoot ($name.Replace('/', '\'))
        if (Test-Path -LiteralPath $overlayPath -PathType Leaf) {
            $replacementPath = $overlayPath
            [void]$replaced.Add($name)
        }
    }

    [byte[]]$header = New-Object byte[] 110
    [Array]::Copy($inputBytes, $offset, $header, 0, 110)
    [byte[]]$replacementBytes = $null
    if ($replacementPath -and (Test-RootfsTextEntry $name)) {
        [byte[]]$rawBytes = [IO.File]::ReadAllBytes($replacementPath)
        $text = [Text.Encoding]::UTF8.GetString($rawBytes)
        $text = $text.Replace("`r`n", "`n").Replace("`r", "`n")
        $replacementBytes = [Text.UTF8Encoding]::new($false).GetBytes($text)
    }
    $newSize = if ($null -ne $replacementBytes) {
        $replacementBytes.LongLength
    } elseif ($replacementPath) {
        (Get-Item -LiteralPath $replacementPath).Length
    } else {
        $fileSize
    }
    if ($newSize -gt [uint32]::MaxValue) {
        throw "newc payload is too large: $replacementPath"
    }
    $sizeText = ([uint32]$newSize).ToString('x8')
    [Text.Encoding]::ASCII.GetBytes($sizeText).CopyTo($header, 54)
    $output.Write($header, 0, $header.Length)
    $output.Write($inputBytes, $nameStart, $nameSize)
    Write-ZeroPadding $output ((Get-Aligned4 $output.Position) - $output.Position)

    if ($null -ne $replacementBytes) {
        $output.Write($replacementBytes, 0, $replacementBytes.Length)
    } elseif ($replacementPath) {
        $source = [IO.File]::OpenRead($replacementPath)
        try {
            $source.CopyTo($output)
        } finally {
            $source.Dispose()
        }
    } elseif ($fileSize -gt 0) {
        $output.Write($inputBytes, $dataStart, [int]$fileSize)
    }
    Write-ZeroPadding $output ((Get-Aligned4 $output.Position) - $output.Position)
    $offset = [int]$nextOffset
}

if (!$foundTrailer) {
    throw 'Baseline rootfs has no newc TRAILER!!! entry'
}

$nextInode = $maxInode + [uint32]1
$overlayPrefix = $overlayRoot.TrimEnd('\') + '\'
$overlayItems = @(Get-ChildItem -LiteralPath $overlayRoot -Recurse -Force |
    Sort-Object @{ Expression = {
        ($_.FullName.Substring($overlayPrefix.Length) -split '[\\/]').Count
    } }, @{ Expression = 'FullName' })
foreach ($item in $overlayItems) {
    $name = $item.FullName.Substring($overlayPrefix.Length).Replace('\', '/')
    if ($seen.Contains($name)) { continue }
    if ($item.PSIsContainer) {
        $mode = 0x41ed
        $dataPath = $null
    } else {
        $executable = $name.StartsWith('etc/init.d/') -or
            $name.StartsWith('bin/') -or $name.StartsWith('sbin/') -or
            $name.StartsWith('usr/bin/') -or $name.StartsWith('usr/sbin/')
        $mode = if ($executable) { 0x81ed } else { 0x81a4 }
        $dataPath = $item.FullName
        [void]$replaced.Add($name)
    }
    Write-NewcEntry $output $name $mode $nextInode $dataPath
    $nextInode++
    [void]$seen.Add($name)
}

foreach ($payload in $payloads) {
    $parts = $payload.Name -split '/'
    $parent = ''
    for ($i = 0; $i -lt $parts.Length - 1; $i++) {
        $parent = if ($parent) { "$parent/$($parts[$i])" } else { $parts[$i] }
        if (!$seen.Contains($parent)) {
            Write-NewcEntry $output $parent 0x41ed $nextInode $null
            $nextInode++
            [void]$seen.Add($parent)
        }
    }
    if (!$seen.Contains($payload.Name)) {
        Write-NewcEntry $output $payload.Name $payload.Mode $nextInode $payload.Path
        $nextInode++
        [void]$seen.Add($payload.Name)
    }
}

foreach ($name in @('etc/inittab', 'etc/profile', 'etc/init.d/rcS')) {
    if (!$replaced.Contains($name)) {
        throw "Rootfs entry was not replaced: $name"
    }
}
foreach ($name in @('etc/init.d/S95pikafish', 'usr/bin/xiangqi-pikafish')) {
    if (!$seen.Contains($name)) {
        throw "Rootfs overlay entry is missing: $name"
    }
}
if ($IncludePikafish) {
    foreach ($payload in $payloads) {
        if (!$seen.Contains($payload.Name)) {
            throw "Pikafish rootfs entry is missing: $($payload.Name)"
        }
    }
}

Write-NewcEntry $output 'TRAILER!!!' 0 $nextInode $null
Write-ZeroPadding $output ((512 - ($output.Length % 512)) % 512)
if ($output.Length -gt $rootfsLimit) {
    throw ("Rootfs exceeds the 80 MiB boot slot: {0} bytes" -f $output.Length)
}

[IO.Directory]::CreateDirectory((Split-Path -Parent $OutputPath)) | Out-Null
$destination = [IO.File]::Create($OutputPath)
try {
    $output.Position = 0
    $output.CopyTo($destination)
} finally {
    $destination.Dispose()
    $output.Dispose()
}

$length = (Get-Item -LiteralPath $OutputPath).Length
$initrdEnd = 0x03000000L + $length
if (!$SkipDtbUpdate) {
    $dtsPath = Join-Path $root 'linux\soc.dts'
    $dtbPath = Join-Path $root 'linux\boot\soc.dtb'
    $dtsText = [IO.File]::ReadAllText($dtsPath)
    $pattern = '(?m)^(\s*linux,initrd-end\s*=\s*<)0x[0-9a-fA-F]+(>;\s*)$'
    $matches = [regex]::Matches($dtsText, $pattern)
    if ($matches.Count -ne 1) {
        throw "Expected one linux,initrd-end property in $dtsPath"
    }
    $endText = '0x{0:x8}' -f $initrdEnd
    $updatedDts = [regex]::Replace($dtsText, $pattern, {
        param($match)
        return $match.Groups[1].Value + $endText + $match.Groups[2].Value
    })
    if ($updatedDts -ne $dtsText) {
        [IO.File]::WriteAllText($dtsPath, $updatedDts,
            [Text.UTF8Encoding]::new($false))
    }
    $wslDts = Convert-ToWslPath $dtsPath
    $wslDtb = Convert-ToWslPath $dtbPath
    & wsl.exe -d $Distro -- dtc -I dts -O dtb -o $wslDtb $wslDts
    if ($LASTEXITCODE -ne 0) {
        throw "DTB compilation failed in WSL distro $Distro"
    }
}

Write-Host "Rootfs: $OutputPath"
Write-Host "Bytes: $length"
Write-Host ('DTS linux,initrd-end: 0x{0:x8}' -f $initrdEnd)
if ($IncludePikafish) {
    $mode = if ($ExternalPff1) { 'external-pff1' } elseif ($EmbeddedOnly) {
        'embedded-only'
    } else { 'full-tools' }
    Write-Host "PIKAFISH_ROOTFS_READY mode=$mode model_sha256=$modelHash"
}
