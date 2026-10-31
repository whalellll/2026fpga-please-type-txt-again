param(
    [string]$KitRoot = '',
    [Parameter(Mandatory=$true)][string]$Destination,
    [switch]$Apply,
    [string]$BackupRoot = '',
    [switch]$DedicatedTrial,
    [switch]$Integrated60Trial,
    [switch]$Integrated60LineFix,
    [switch]$IntegratedOpt60
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
if ($IntegratedOpt60) {
    if ($DedicatedTrial -or $Integrated60Trial -or $Integrated60LineFix) { throw 'Choose one hardware profile.' }
    $sourceRoot=Split-Path -Parent $PSScriptRoot
    $candidatePath=Join-Path $sourceRoot 'artifacts/integrated_opt60_resource_p3_20261024/manifest.json'
    $candidate=Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8|ConvertFrom-Json
    $bitPath=Join-Path $sourceRoot 'artifacts/integrated_opt60_resource_p3_20261024/soc_top.sbit'
    $run='06a580c5937e413fbf7e3d843e465594'
    if ($manifest.status -cne 'INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' -or
        $manifest.binding_status -cne 'OPT60_P3_EXACT_NATIVE_IDENTICAL_SOFTWARE_BOUND_NOT_BOARD' -or
        $manifest.candidate_run_id -cne $run -or $candidate.run_id -cne $run -or
        $candidate.status -cne 'INTEGRATED_OPT60_FULL_NATIVE_STA_PASS_NOT_BOARD' -or !$candidate.final_sta_pass -or
        $candidate.source_commit -cne '8aae985849f8f44e3c898dbcf31234a8df680f95' -or
        $manifest.candidate_bitstream_sha256 -cne $candidate.bitstream.sha256 -or
        $manifest.candidate_manifest_sha256 -cne (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $manifest.candidate_bitstream_sha256 -cne (Get-FileHash -LiteralPath $bitPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $manifest.cpu_hz -ne 60000000 -or $manifest.sys_hz -ne 49500000 -or
        !$manifest.optimization_candidate -or !$manifest.original_picture_weights -or !$manifest.voice_stream_enabled -or !$manifest.voice_quant_enabled -or
        @($manifest.tests).Count -ne 18 -or $manifest.board_tested -ne $false) { throw 'Optimized CPU60 exact native/SD binding differs.' }
    $expectedNames=@('Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb')
    if ((@($manifest.sd_root_files.PSObject.Properties.Name | Sort-Object) -join ',') -ne (@($expectedNames | Sort-Object) -join ',')) { throw 'Incomplete optimized SD eight-file contract.' }
    foreach($name in $manifest.tests){
        if($name -match '[\\/:]' -or $name -in @('.','..')){throw 'Unsafe loader test path'}
        if(![IO.File]::ReadAllText((Join-Path $package ('evidence/'+$name))).Contains('HOST_TEST_PASS')){throw "Loader test did not pass: $name"}
    }
} elseif ($Integrated60Trial -or $Integrated60LineFix) {
    if ($DedicatedTrial) { throw 'Choose one hardware profile.' }
    if ($Integrated60Trial -and $Integrated60LineFix) { throw 'Choose one integrated60 hardware revision.' }
    $sourceRoot=Split-Path -Parent $PSScriptRoot
    $candidateDir=if($Integrated60LineFix){'artifacts/integrated60_linefix_20261024'}else{'artifacts/integrated60_20261024'}
    $candidatePath=Join-Path $sourceRoot ($candidateDir+'/manifest.json')
    $candidate=Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8|ConvertFrom-Json
    $bitPath=Join-Path $sourceRoot ($candidateDir+'/soc_top.sbit')
    $run=if($Integrated60LineFix){'dc951f8b1b7f4cf9962e5f509f165d0f'}else{'866e820244ee4303a0295d68fe190076'}
    if($Integrated60LineFix -and (!$candidate.strict_original_flow_pass -or !$candidate.native_line_fix -or !$manifest.voice_stream_enabled)){throw 'Require full STA, native-line RTL fix and streamed voice runtime.'}
    if ($manifest.status -cne 'INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' -or
        $manifest.candidate_run_id -cne $run -or $candidate.run_id -cne $run -or
        $manifest.candidate_bitstream_sha256 -cne $candidate.bitstream.sha256 -or
        $manifest.candidate_manifest_sha256 -cne (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $manifest.candidate_bitstream_sha256 -cne (Get-FileHash -LiteralPath $bitPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
        !($candidate.independent_review_pass -or $candidate.strict_original_flow_pass) -or !$candidate.sta_pass -or
        $manifest.cpu_hz -ne 60000000 -or $manifest.sys_hz -ne 49500000 -or
        !$manifest.original_picture_weights -or @($manifest.tests).Count -ne 18 -or $manifest.board_tested -ne $false) { throw 'CPU60 integrated original-model timing binding differs.' }
    $expectedNames=@('Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb')
    if ((@($manifest.sd_root_files.PSObject.Properties.Name | Sort-Object) -join ',') -ne (@($expectedNames | Sort-Object) -join ',')) { throw 'Incomplete integrated60 SD contract.' }
    foreach($name in $manifest.tests){
        if($name -match '[\\/:]' -or $name -in @('.','..')){throw 'Unsafe loader test path'}
        if(![IO.File]::ReadAllText((Join-Path $package ('evidence/'+$name))).Contains('HOST_TEST_PASS')){throw "Loader test did not pass: $name"}
    }
} elseif ($DedicatedTrial) {
    $trial=Get-Content -LiteralPath (Join-Path $package 'trial-binding.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.status -ne 'VOICE_NNUE_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' -or
        $trial.status -ne 'PIKAFISH_DEDICATED_SD_OFFLINE_READY_BOARD_PENDING_STA_FAILED' -or
        $trial.run_id -ne '6a6729f83eae4ad4bd137f3f19b3fd39' -or
        $trial.bitstream_sha256 -ne '23070de4e8da144b148a67a5fb4e2753e9887edbc03d94dd3bc6e18287eaeca0' -or
        $trial.manifest_sha256 -cne (Get-FileHash -LiteralPath (Join-Path $package 'manifest.json')).Hash.ToLowerInvariant() -or
        $trial.bitstream_sha256 -cne (Get-FileHash -LiteralPath (Join-Path $package 'soc_top.sbit')).Hash.ToLowerInvariant() -or
        $manifest.cpu_hz -ne 75000000 -or $manifest.sys_hz -ne 49500000 -or
        !$manifest.pipeline_integration_sha256 -or
        @($manifest.tests).Count -ne 18 -or $manifest.board_tested -ne $false -or $trial.delivery -ne $false) { throw 'Dedicated trial binding mismatch.' }
    $expectedNames=@('Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb')
    if ((@($manifest.sd_root_files.PSObject.Properties.Name | Sort-Object) -join ',') -ne (@($expectedNames | Sort-Object) -join ',')) { throw 'Incomplete dedicated SD contract.' }
    foreach ($name in $manifest.tests) {
        if ($name -match '[\\/:]' -or $name -in @('.','..')) { throw 'Unsafe loader test log path.' }
        if (![IO.File]::ReadAllText((Join-Path $package ('evidence/' + $name))).Contains('HOST_TEST_PASS')) { throw "Loader test did not pass: $name" }
    }
} elseif ($manifest.status -notin @('CPU80_CONV_SD_OFFLINE_VERIFIED_BOARD_PENDING','AUDIO_SERVICE_SD_18_OFFLINE_TESTS_PASS_BOARD_PENDING')) { throw 'Unexpected SD package status.' }
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
Write-Output 'Safely remove the SD card in Windows, return it to the board, then use soc> sdboot with the exact matching candidate bitstream. Board acceptance remains pending.'
