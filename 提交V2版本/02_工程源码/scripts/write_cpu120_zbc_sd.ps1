param(
 [Parameter(Mandatory=$true)][string]$PackageRoot,
 [Parameter(Mandatory=$true)][string]$ArchivePath,
 [Parameter(Mandatory=$true)][string]$VerificationReceipt,
 [Parameter(Mandatory=$true)][string]$OutputDirectory,
 [Parameter(Mandatory=$true)][ValidatePattern('^[A-Z]$')][string]$TargetDrive,
 [Parameter(Mandatory=$true)][int]$ExpectedDiskNumber,
 [Parameter(Mandatory=$true)][string]$ExpectedDiskUniqueId,
 [Parameter(Mandatory=$true)][string]$ExpectedVolumeId
)
$ErrorActionPreference = 'Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$kit=Join-Path $PackageRoot 'software/cpu120/sd'
$out=[IO.Path]::GetFullPath($OutputDirectory)
$archiveHash=(Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$verified=Get-Content -LiteralPath $VerificationReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if($verified.status -ne 'CPU120_ZIP_INDEPENDENT_UNPACK_CPU134_ARCH9_SOC_FC1_38_REGRESSION_PASS_MEDIA_PENDING' -or $verified.archive_sha256 -ne $archiveHash -or [IO.Path]::GetFullPath((Join-Path $verified.extraction 'SOC')) -ne $PackageRoot){throw 'Archive and independent verified extraction differ.'}
$targetRoot=$TargetDrive+':/'

if (Test-Path -LiteralPath $out) { throw 'Receipt directory already exists.' }
function Get-CardIdentity {
 $partition=Get-Partition -DriveLetter $TargetDrive
 $disk=$partition|Get-Disk; $volume=Get-Volume -DriveLetter $TargetDrive
 if($disk.Number -ne $ExpectedDiskNumber -or $disk.UniqueId -cne $ExpectedDiskUniqueId -or $volume.UniqueId -cne $ExpectedVolumeId -or $disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem -or $disk.IsReadOnly -or $volume.FileSystem -ne 'FAT32'){throw 'Fresh removable SD identity differs.'}
 if($disk.Size -ne 31914983424 -or $disk.Signature -ne 485309763 -or $partition.PartitionNumber -ne 1 -or $partition.Offset -ne 16384 -or $partition.Size -ne 31914852352 -or [string]$disk.PartitionStyle -ne 'MBR'){throw 'This release writer is scoped to the accepted 31GB FAT32 card; inspect another medium separately.'}
 [ordered]@{disk=$disk.Number;model=$disk.FriendlyName;serial=$disk.SerialNumber;bus=[string]$disk.BusType;disk_bytes=$disk.Size;volume_id=$volume.UniqueId;filesystem=$volume.FileSystem;free_bytes=$volume.SizeRemaining;disk_unique_id=$disk.UniqueId}
}
function Hash-File([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Regular-File([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Not a regular file: $path" }
    $item
}
function Copy-Durable([string]$source,[string]$target) {
    $inputFile = [IO.File]::OpenRead($source)
    try {
        $outputFile = [IO.FileStream]::new($target,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None,1048576,[IO.FileOptions]::WriteThrough)
        try { $inputFile.CopyTo($outputFile); $outputFile.Flush($true) } finally { $outputFile.Dispose() }
    } finally { $inputFile.Dispose() }
}
$identity = Get-CardIdentity
$manifestPath = Join-Path $kit 'manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$verification = Get-Content -LiteralPath (Join-Path $kit 'verification.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.status -ne 'JOINT_CPU120_ZBC_SD8_RUNTIME_IDENTITY_REBOUND_STATIC_HASH_CRC_PASS_BOARD_PENDING' -or
    $manifest.cpu_hz -ne 120000000 -or $verification.manifest_sha256 -ne (Hash-File $manifestPath)) { throw 'Candidate manifest binding differs.' }
$independentPath=Join-Path $kit 'independent-verification.json'
$independent=Get-Content -LiteralPath $independentPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($independent.status -ne 'JOINT_CPU120_ZBC_SD8_INDEPENDENT_BINDINGS_CPIO_ALL_UNCHANGED_METADATA_DTB_PAYLOAD_RUNTIME_PASS_NOT_BOARD' -or $independent.kit_manifest_sha256 -ne (Hash-File $manifestPath)) {throw 'Independent SD verification missing or stale'}
$names = @('Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb')
if ((@($manifest.sd_root_files.PSObject.Properties.Name | Sort-Object) -join ',') -ne (($names | Sort-Object) -join ',')) { throw 'Eight-file inventory differs.' }
$plan = @()
foreach ($name in $names + @('SHA256SUMS.txt')) {
    $source = Join-Path $PackageRoot ('linux/boot/' + $name)
    $item = Regular-File $source
    $hash = Hash-File $source
    if ($name -ne 'SHA256SUMS.txt' -and ($hash -ne $manifest.sd_root_files.$name.sha256 -or $item.Length -ne $manifest.sd_root_files.$name.bytes)) { throw "Source differs: $name" }
    $target = Join-Path $targetRoot $name
    $oldHash = $null
    if (Test-Path -LiteralPath $target) { $null = Regular-File $target; $oldHash = Hash-File $target }
    $plan += [ordered]@{name=$name;source=$source;target=$target;bytes=$item.Length;sha256=$hash;previous_sha256=$oldHash;changed=($hash -ne $oldHash)}
}
$checksum = [IO.File]::ReadAllLines((Join-Path $PackageRoot 'linux/boot/SHA256SUMS.txt'))
if ($checksum.Count -ne 8) { throw 'Checksum file must list exactly eight files.' }
foreach ($name in $names) {
    if (($manifest.sd_root_files.$name.sha256 + '  ' + $name) -notin $checksum) { throw "Checksum inventory differs: $name" }
}
New-Item -ItemType Directory -Path $out | Out-Null
$backup = Join-Path $out 'backup'
New-Item -ItemType Directory -Path $backup | Out-Null
$record = [ordered]@{archive_sha256=$archiveHash;independent_verification_sha256=(Hash-File $VerificationReceipt);package_root=$PackageRoot;target_drive=$TargetDrive;status='SD_PREWRITE_BACKUP_RUNNING';started_utc=[DateTime]::UtcNow.ToString('o');identity=$identity;kit_manifest_sha256=(Hash-File $manifestPath);files=$plan;root_before=@();directories_before=@();readback=@();physical_media_written=$false;card_formatted=$false;flash_written=$false;board_tested=$false;formal_delivery_complete=$false}
function Save-Receipt { $record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8 }
Save-Receipt
try {
    $record.directories_before = @(Get-ChildItem -LiteralPath $targetRoot -Force -Directory | ForEach-Object Name | Sort-Object)
    foreach ($file in Get-ChildItem -LiteralPath $targetRoot -Force -File) {
        $null = Regular-File $file.FullName
        $record.root_before += [ordered]@{name=$file.Name;bytes=$file.Length;last_write_utc=$file.LastWriteTimeUtc.ToString('o');sha256=$(if ($file.Name -in ($names + @('SHA256SUMS.txt'))) { Hash-File $file.FullName } else { $null })}
    }
    foreach ($row in $plan | Where-Object { $_.changed -and $_.previous_sha256 }) {
        $saved = Join-Path $backup $row.name
        Copy-Durable $row.target $saved
        if ((Hash-File $saved) -ne $row.previous_sha256) { throw "Backup differs: $($row.name)" }
        $row.backup = $saved
    }
    $record.status = 'SD_BACKUP_VERIFIED_READY_TO_WRITE'; Save-Receipt
    $null = Get-CardIdentity
    foreach ($row in $record.root_before | Where-Object sha256) {
        if ((Hash-File (Join-Path $targetRoot $row.name)) -ne $row.sha256) { throw "Card changed before write: $($row.name)" }
    }
    foreach ($row in $plan | Where-Object changed) {
        $null = Get-CardIdentity
        $record.status = 'SD_WRITING'; $record.physical_media_written = $true; Save-Receipt
        Copy-Durable $row.source $row.target
        Write-Output "WRITTEN $($row.name)"
    }
    Write-VolumeCache -DriveLetter $TargetDrive
    $record.volume_cache_flushed = $true
    $null = Get-CardIdentity
    foreach ($row in $plan) {
        $item = Regular-File $row.target
        $actual = Hash-File $row.target
        if ($actual -ne $row.sha256 -or $item.Length -ne $row.bytes) { throw "Readback differs: $($row.name)" }
        $record.readback += [ordered]@{name=$row.name;bytes=$item.Length;sha256=$actual}
    }
    foreach ($row in $record.root_before | Where-Object { $_.name -notin ($names + @('SHA256SUMS.txt')) }) {
        if ((Get-Item -LiteralPath (Join-Path $targetRoot $row.name)).Length -ne $row.bytes -or (Get-Item -LiteralPath (Join-Path $targetRoot $row.name)).LastWriteTimeUtc.ToString('o') -ne $row.last_write_utc) { throw "Unrelated root file metadata differs: $($row.name)" }
    }
    if ((@(Get-ChildItem -LiteralPath $targetRoot -Force -Directory | ForEach-Object Name | Sort-Object) -join '|') -ne ($record.directories_before -join '|')) { throw 'User directory inventory changed.' }
    $expectedRoot = @(($record.root_before | ForEach-Object name) + ($plan | ForEach-Object name) | Sort-Object -Unique)
    if ((@(Get-ChildItem -LiteralPath $targetRoot -Force -File | ForEach-Object Name | Sort-Object) -join '|') -ne ($expectedRoot -join '|')) { throw 'Unexpected root file inventory.' }
    $record.status = 'CPU120_ZBC_ZIP_BOUND_SD8_WRITE_FLUSH_READBACK_PASS_DIRECT_SD_BOOT_PENDING'
    $record.user_directories_preserved = $true
    $record.unrelated_root_files_metadata_unchanged = $true
    $record.ready_for_safe_removal = $true
    $record.restore_command = 'Copy the files listed with backup paths in this receipt from sd120-write-01/backup to the identity-checked E:/ root, flush volume cache, and verify previous_sha256. Unchanged files need no restoration.'
} catch {
    $record.status = 'SD_WRITE_INCOMPLETE_PRESERVED'
    $record.error = $_.Exception.Message
    throw
} finally {
    $record.completed_utc = [DateTime]::UtcNow.ToString('o')
    Save-Receipt
}
Write-Output $record.status
