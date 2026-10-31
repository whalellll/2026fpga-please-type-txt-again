param([Parameter(Mandatory=$true)][string]$TargetRoot,
      [Parameter(Mandatory=$true)][string]$PackageDirectory,
      [Parameter(Mandatory=$true)][string]$BackupDirectory)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($TargetRoot)
if($target -cne 'F:\'){throw 'This operation is authorized only for the user-selected F:\ card'}
$package=[IO.Path]::GetFullPath($PackageDirectory)
$backup=[IO.Path]::GetFullPath($BackupDirectory)
if(Test-Path -LiteralPath $backup){throw 'Choose a fresh PC backup directory'}
if(-not $backup.StartsWith('D:\LJL\WORK\GitHub\performance_soc\build\',[StringComparison]::OrdinalIgnoreCase)){throw 'PC backup must remain under build/'}
$manifest=Get-Content -LiteralPath (Join-Path $package 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$volume=Get-Volume -DriveLetter F
$partition=Get-Partition -DriveLetter F
$disk=$partition | Get-Disk
if($volume.DriveType -ne 'Removable' -or $volume.FileSystemType -ne 'FAT32' -or
   $volume.Size -ne 31906463744 -or $disk.Size -ne 31914983424 -or
   $disk.BusType -ne 'USB' -or $disk.Number -ne 1){throw 'Selected SD identity changed'}
$identity=[ordered]@{drive='F:\';volume_unique_id=$volume.UniqueId;disk_unique_id=$disk.UniqueId;
    disk_number=$disk.Number;disk_bytes=$disk.Size;volume_bytes=$volume.Size;
    filesystem=$volume.FileSystemType;bus_type=[string]$disk.BusType;partition_offset=$partition.Offset;
    authorization='User explicitly selected F:\ for this SD update';cid='Not exposed by this Windows USB reader; no CID claim'}
function Assert-SameCard {
    $v=Get-Volume -DriveLetter F;$d=Get-Partition -DriveLetter F | Get-Disk
    if($v.UniqueId -ne $identity.volume_unique_id -or $d.UniqueId -ne $identity.disk_unique_id -or
       $v.Size -ne $identity.volume_bytes -or $d.Size -ne $identity.disk_bytes){throw 'F:\ target changed'}
}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Copy-Flushed([string]$Source,[string]$Destination){
    $inputStream=[IO.File]::OpenRead($Source)
    $outputStream=[IO.FileStream]::new($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,
        [IO.FileShare]::None,1048576,[IO.FileOptions]::WriteThrough)
    try{$inputStream.CopyTo($outputStream,1048576);$outputStream.Flush($true)}
    finally{$outputStream.Dispose();$inputStream.Dispose()}
}
foreach($entry in $manifest.unchanged_sd_dependencies.PSObject.Properties){
    $path=Join-Path $target $entry.Name
    if((Get-Item -LiteralPath $path).Length -ne $entry.Value.bytes -or (Sha $path) -ne $entry.Value.sha256){throw ('SD dependency mismatch: '+$entry.Name)}
}
$original=Join-Path $target 'xiangqi.bin'
if((Sha $original) -ne 'b5c1f41493fd9617622a341ccf8fb266dc20f841fff7ee2440ceb5f508cf5969'){throw 'Unexpected old boot entry; stop before writes'}
$temporary=@{'N20K.BIN'='N20K.NEW';'N20FS.BIN'='N20FS.NEW';'N20.DTB'='N20.NEW';'xiangqi.bin'='XQ20.NEW'}
foreach($name in $temporary.Keys){
    $source=Join-Path (Join-Path $package 'sd-root') $name
    $entry=$manifest.files.$name
    if((Sha $source) -ne $entry.sha256 -or (Get-Item -LiteralPath $source).Length -ne $entry.bytes){throw ('Package mismatch: '+$name)}
    if(Test-Path -LiteralPath (Join-Path $target $temporary[$name])){throw 'SD staging name already exists'}
    if($name -ne 'xiangqi.bin' -and (Test-Path -LiteralPath (Join-Path $target $name))){throw 'New SD target already exists'}
}
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Flushed $original (Join-Path $backup 'xiangqi.bin')
if((Sha (Join-Path $backup 'xiangqi.bin')) -ne (Sha $original)){throw 'Old boot backup verification failed'}
$identity | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backup 'target.json') -Encoding UTF8
foreach($name in @('N20K.BIN','N20FS.BIN','N20.DTB','xiangqi.bin')){
    Assert-SameCard
    $staged=Join-Path $target $temporary[$name]
    Copy-Flushed (Join-Path (Join-Path $package 'sd-root') $name) $staged
    if((Sha $staged) -ne $manifest.files.$name.sha256){throw ('Staged SD readback mismatch: '+$name)}
}
# Publish the entry last; the original entry is already backed up on the PC.
foreach($name in @('N20K.BIN','N20FS.BIN','N20.DTB','xiangqi.bin')){
    Assert-SameCard
    Move-Item -LiteralPath (Join-Path $target $temporary[$name]) -Destination (Join-Path $target $name) -Force
}
Assert-SameCard
$readback=[ordered]@{}
foreach($name in @('N20K.BIN','N20FS.BIN','N20.DTB','xiangqi.bin')){
    $path=Join-Path $target $name;$item=Get-Item -LiteralPath $path
    $digest=Sha $path
    if($digest -ne $manifest.files.$name.sha256 -or $item.Length -ne $manifest.files.$name.bytes){throw ('Published SD readback mismatch: '+$name)}
    $readback[$name]=[ordered]@{bytes=$item.Length;sha256=$digest}
}
if((Sha (Join-Path $target 'Image')) -ne '6ca0bdd3f3490c1b38606a80dd4912c5c2ffce08bc165abf00f13806f5f0c1e0'){throw 'Original Image identity changed'}
$receipt=[ordered]@{schema_version=1;status='FILES_WRITTEN_AND_READBACK_VERIFIED';recorded_utc=[DateTime]::UtcNow.ToString('o');
    device=$identity;package_manifest_sha256=(Sha (Join-Path $package 'manifest.json'));
    files=$readback;pc_backup_directory=$backup;old_entry_sha256=(Sha (Join-Path $backup 'xiangqi.bin'));
    original_Image_preserved=$true;sd_written=$true;flash_written=$false;board_boot_validated=$false;
    per_file_flush_to_disk=$true;safe_eject_required_before_removal=$true}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backup 'installation.json') -Encoding UTF8
Write-Output 'NATIVE_SD_FILES_WRITTEN_AND_READBACK_VERIFIED safe_eject_required=true board_boot_validated=false'
Write-Output ('PC_BACKUP='+$backup)
