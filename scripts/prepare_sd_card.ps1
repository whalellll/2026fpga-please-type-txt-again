param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [switch]$IncludeSong,
    [ValidateSet('All', 'Linux', 'Xiangqi')]
    [string]$Content = 'All'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$bootRoot = Join-Path $repoRoot 'linux\boot'
$resolvedDestination = Resolve-Path -LiteralPath $Destination
if ($resolvedDestination.Provider.Name -ne 'FileSystem') {
    throw 'Destination must be a filesystem directory.'
}
$destinationPath = $resolvedDestination.ProviderPath

if (!(Test-Path -LiteralPath $destinationPath -PathType Container)) {
    throw "Destination is not a directory: $destinationPath"
}
if ((Get-Item -LiteralPath $destinationPath -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
    throw "Destination must not be a reparse point: $destinationPath"
}

$volumeRoot = [IO.Path]::GetPathRoot($destinationPath)
if ($destinationPath.TrimEnd('\') -ne $volumeRoot.TrimEnd('\')) {
    throw 'Destination must be the Micro SD volume root; boot files belong in the FAT root directory.'
}
if ($volumeRoot -notmatch '^[A-Za-z]:\\$') {
    throw "Destination must be a local drive-letter root: $destinationPath"
}
$volume = [IO.DriveInfo]::new($volumeRoot)
if (!$volume.IsReady) {
    throw "Micro SD volume is not ready: $volumeRoot"
}
if ($volume.DriveFormat -notin @('FAT', 'FAT32')) {
    throw "Micro SD must be FAT16/FAT32, not $($volume.DriveFormat). This script never formats media."
}
if ($volume.DriveFormat -eq 'FAT') {
    Write-Warning 'Windows reports FAT generically; the bootloader supports FAT16, not FAT12. Confirm with sdinfo before booting.'
}

function Get-RegularFile {
    param([string]$Path, [switch]$AllowMissing)
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    } catch [System.Management.Automation.ItemNotFoundException] {
        if ($AllowMissing) { return $null }
        throw
    }
    if ($item.PSIsContainer -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $item -isnot [IO.FileInfo]) {
        throw "Expected a regular file, not a directory/reparse point: $Path"
    }
    return $item
}

$linuxNames = @('fw_jump.bin', 'Image', 'rootfs.cpio', 'soc.dtb',
    'pikafish.pff', 'pikafish.atk')
$xiangqiNames = @('xqmodel.bin', 'xiangqi.bin')
$names = switch ($Content) {
    'Linux'   { $linuxNames }
    'Xiangqi' { $xiangqiNames }
    default   { $linuxNames + $xiangqiNames }
}
if ($IncludeSong) { $names += 'SONG.PCM' }
$plan = @()

# Preflight the entire requested group before creating any file on the card.
foreach ($name in $names) {
    $source = if ($name -eq 'SONG.PCM') {
        Join-Path $repoRoot 'artifacts\SONG.PCM'
    } else {
        Join-Path $bootRoot $name
    }
    $target = Join-Path $destinationPath $name
    $sourceItem = Get-RegularFile -Path $source
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($name -eq 'SONG.PCM') {
        $expectedSongBytes = 6162968L
        $expectedSongHash =
            '863f5f298c2dde0cfda90fff23f6af748e780cc8967c310727591f648bed88dd'
        if ($sourceItem.Length -ne $expectedSongBytes -or
                $sourceHash -ne $expectedSongHash) {
            throw 'SONG.PCM length/SHA256 mismatch; run scripts\make_song_pcm.ps1 -ValidateOnly.'
        }
    }
    $targetItem = Get-RegularFile -Path $target -AllowMissing
    if ($null -ne $targetItem) {
        $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($targetItem.Length -ne $sourceItem.Length -or $targetHash -ne $sourceHash) {
            throw "Existing file differs from release input; nothing was copied: $target"
        }
    }
    $plan += [pscustomobject]@{
        Name = $name; Source = $source; Target = $target
        Bytes = $sourceItem.Length; Hash = $sourceHash
        Missing = ($null -eq $targetItem)
    }
}

foreach ($entry in $plan) {
    if ($entry.Missing) {
        $temporaryPath = Join-Path $destinationPath (
            '.prepare_sd_' + [guid]::NewGuid().ToString('N') + '.part')
        $temporaryCreated = $false
        $inputStream = $null
        $outputStream = $null
        try {
            # CreateNew and the two-argument File.Move both refuse overwrite,
            # including a target that appeared after the group preflight.
            $outputStream = [IO.File]::Open($temporaryPath,
                [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $temporaryCreated = $true
            $inputStream = [IO.File]::Open($entry.Source,
                [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
            $inputStream.CopyTo($outputStream)
            $outputStream.Flush($true)
            $inputStream.Dispose()
            $inputStream = $null
            $outputStream.Dispose()
            $outputStream = $null
            $temporaryItem = Get-RegularFile -Path $temporaryPath
            $temporaryHash = (Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash
            if ($temporaryItem.Length -ne $entry.Bytes -or $temporaryHash -ne $entry.Hash) {
                throw "Copy verification failed before publishing: $($entry.Name)"
            }
            [IO.File]::Move($temporaryPath, $entry.Target)
            $temporaryCreated = $false
        } finally {
            if ($null -ne $inputStream) { $inputStream.Dispose() }
            if ($null -ne $outputStream) { $outputStream.Dispose() }
            if ($temporaryCreated) {
                Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction Stop
            }
        }
    }
    $targetItem = Get-RegularFile -Path $entry.Target
    $targetHash = (Get-FileHash -LiteralPath $entry.Target -Algorithm SHA256).Hash
    if ($targetItem.Length -ne $entry.Bytes -or $targetHash -ne $entry.Hash) {
        throw "Final file verification failed: $($entry.Name)"
    }
    $action = if ($entry.Missing) { 'COPIED' } else { 'VERIFIED_EXISTING' }
    Write-Output ("{0,-14} {1,10} bytes  SHA256={2} {3}" -f
        $entry.Name, $targetItem.Length, $targetHash.ToLowerInvariant(), $action)
}

Write-Output "MICRO_SD_BOOT_FILES_READY content=$Content destination=$destinationPath"
if ($IncludeSong) {
    Write-Output "MICRO_SD_SPEAKER_MEDIA_READY destination=$destinationPath"
}
