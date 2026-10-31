param(
    [string]$KitRoot = '',
    [Parameter(Mandatory=$true)][string]$Destination,
    [switch]$Apply,
    [string]$BackupRoot = ''
)
$ErrorActionPreference = 'Stop'
if (!$KitRoot) {
    $KitRoot = $PSScriptRoot
    if (!(Test-Path -LiteralPath (Join-Path $KitRoot 'manifest.json') -PathType Leaf)) {
        $KitRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/cpu80_conv_sdboot_20261022/sd-kit'
    }
}
if (!$BackupRoot) { $BackupRoot = Join-Path $KitRoot 'backups' }
$package = [IO.Path]::GetFullPath($KitRoot)
$manifest = Get-Content -LiteralPath (Join-Path $package 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.status -notin @('CPU80_CONV_SD_OFFLINE_VERIFIED_BOARD_PENDING','AUDIO_SERVICE_SD_18_OFFLINE_TESTS_PASS_BOARD_PENDING')) { throw 'Unexpected SD package status.' }
if ($manifest.status -eq 'AUDIO_SERVICE_SD_18_OFFLINE_TESTS_PASS_BOARD_PENDING') {
    if ($manifest.candidate_run_id -ne '44aa982f752c4b7d91accea60292735f' -or
        $manifest.candidate_bitstream_sha256 -ne '30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1' -or
        @($manifest.tests).Count -ne 18 -or $manifest.board_tested -ne $false) { throw 'Audio-service software kit does not bind the repaired ROM and offline tests.' }
    foreach ($name in $manifest.tests) {
        if ($name -match '[\\/:]' -or $name -in @('.','..')) { throw 'Unsafe loader test log path.' }
        if (![IO.File]::ReadAllText((Join-Path $package ('evidence/' + $name))).Contains('HOST_TEST_PASS')) { throw "Loader test did not pass: $name" }
    }
    $expectedNames=@('Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb')
    if ((@($manifest.sd_root_files.PSObject.Properties.Name | Sort-Object) -join ',') -ne (@($expectedNames | Sort-Object) -join ',')) { throw 'Incomplete SD eight-file contract.' }
}
$destinationPath = (Resolve-Path -LiteralPath $Destination).ProviderPath
if ($destinationPath -notmatch '^[A-Za-z]:\\$') { throw 'Specify the physical SD volume root, such as E:\.' }
$letter = $destinationPath.Substring(0,1)
$partition = Get-Partition -DriveLetter $letter
$disk = Get-Disk -Number $partition.DiskNumber
$volume = Get-Volume -DriveLetter $letter
if ($disk.IsBoot -or $disk.IsSystem -or $disk.IsReadOnly -or $disk.BusType -notin @('USB','SD','MMC')) {
    throw 'Destination must be a writable SD/removable USB card reader, never a system disk.'
}
if ($volume.FileSystem -notin @('FAT','FAT32')) { throw 'Expected FAT16/FAT32. This tool never formats or partitions.' }
if ((Get-Item -LiteralPath $destinationPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse destination refused.' }
$backupAbsolute = [IO.Path]::GetFullPath($BackupRoot)
if ([IO.Path]::GetPathRoot($backupAbsolute) -eq $destinationPath) { throw 'Backup must be on the PC, outside the SD volume.' }
$plan = @()
foreach ($property in $manifest.sd_root_files.PSObject.Properties) {
    $name = $property.Name
    if ($name -match '[\\/:]' -or $name -in @('.','..')) { throw 'Unsafe manifest filename.' }
    $source = Join-Path (Join-Path $package 'sd-root') $name
    $expected = $property.Value.sha256
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "Source hash mismatch: $name" }
    $target = Join-Path $destinationPath $name
    $oldHash = $null
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Unsafe target: $target" }
        $oldHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $plan += [PSCustomObject]@{Name=$name;Source=$source;Target=$target;Expected=$expected;Previous=$oldHash;Copy=($oldHash -ne $expected)}
}
$disk | Select-Object Number,FriendlyName,SerialNumber,BusType,Size,IsBoot,IsSystem | Format-List
$volume | Select-Object DriveLetter,FileSystemLabel,FileSystem,UniqueId,Size,SizeRemaining | Format-List
$plan | Select-Object Name,Copy,Expected | Format-Table -AutoSize
if (!$Apply) { Write-Output 'READ_ONLY_PLAN: inspect disk identity; add -Apply to copy this exact kit.'; return }
$needed = ($plan | Where-Object Copy | ForEach-Object { (Get-Item -LiteralPath $_.Source).Length } | Measure-Object -Sum).Sum
if ($volume.SizeRemaining -lt $needed) { throw 'Insufficient free space for the safe file replacement.' }
$backup = Join-Path $backupAbsolute ('disk{0}-{1}' -f $disk.Number,(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backup | Out-Null
# Back up every changed existing file and verify all backups before any SD write.
foreach ($row in $plan | Where-Object { $_.Copy -and $_.Previous }) {
    $saved = Join-Path $backup $row.Name
    Copy-Item -LiteralPath $row.Target -Destination $saved
    if ((Get-FileHash -LiteralPath $saved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.Previous) { throw "Backup mismatch: $($row.Name)" }
}
$identity = [PSCustomObject]@{DiskNumber=$disk.Number;SerialNumber=$disk.SerialNumber;VolumeId=$volume.UniqueId;PackageManifestSHA256=(Get-FileHash -LiteralPath (Join-Path $package 'manifest.json')).Hash;Files=$plan}
$identity | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $backup 'restore-plan.json') -Encoding UTF8
$freshDisk = Get-Disk -Number (Get-Partition -DriveLetter $letter).DiskNumber
$freshVolume = Get-Volume -DriveLetter $letter
if ($freshDisk.SerialNumber -ne $disk.SerialNumber -or $freshDisk.Number -ne $disk.Number -or $freshVolume.UniqueId -ne $volume.UniqueId) { throw 'Media changed after planning.' }
foreach ($row in $plan | Where-Object Copy) {
    $inputFile = [IO.File]::OpenRead($row.Source)
    try {
        $outputFile = [IO.FileStream]::new($row.Target,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None,1048576,[IO.FileOptions]::WriteThrough)
        try { $inputFile.CopyTo($outputFile); $outputFile.Flush($true) } finally { $outputFile.Dispose() }
    } finally { $inputFile.Dispose() }
}
if (Get-Command Write-VolumeCache -ErrorAction SilentlyContinue) { Write-VolumeCache -DriveLetter $letter }
foreach ($row in $plan) {
    if ((Get-FileHash -LiteralPath $row.Target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.Expected) { throw "SD readback mismatch: $($row.Name)" }
}
[PSCustomObject]@{Status='SD_FILES_WRITTEN_READBACK_HASH_PASS_BOARD_PENDING';Backup=$backup;ManifestSHA256=$identity.PackageManifestSHA256;Disk=$disk.Number;VolumeId=$volume.UniqueId;BoardTested=$false} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backup 'write-result.json') -Encoding UTF8
Write-Output "SD_FILES_WRITTEN_READBACK_HASH_PASS_BOARD_PENDING; PC backup: $backup"
Write-Output 'Safely remove the SD card in Windows, return it to the board, then use soc> sdboot with the matching CPU80 convolution candidate bitstream. Board acceptance remains pending.'
