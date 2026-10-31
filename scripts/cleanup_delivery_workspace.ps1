# Archive only explicitly known disposable output after a completed delivery step.
# Source trees, tracked files, frozen candidates and PDS databases are never selected.
param(
    [ValidateSet('Plan','Apply')][string]$Action = 'Plan',
    [Parameter(Mandatory=$true)][string]$CompletionReceipt,
    [string]$WorkspaceRoot = '',
    [switch]$IncludeLegacySimulationScratch
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
if (!$WorkspaceRoot) { $WorkspaceRoot = Split-Path -Parent $root }
$WorkspaceRoot = [IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd('\')
$utf8 = [Text.UTF8Encoding]::new($false)

function Assert-PlainPath([string]$Path, [string]$Parent) {
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
    if (!$full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes allowed root: $full"
    }
    $cursor = $full
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and
            ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Linked cleanup path: $cursor"
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}

function Assert-NoBuildOwner {
    $active = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -and
        $_.CommandLine.IndexOf($WorkspaceRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($_.Name -match '^(pds_shell|pds|vvp|iverilog)\.exe$' -or
         ($_.Name -match '^(powershell|pwsh|python|python3)\.exe$' -and
          $_.CommandLine -match '(build_fpga|run_all_tests|start_detached_release_job|chain_sixth_native|post_pnr_p6)'))
    })
    if ($active.Count) { throw 'Build/simulation owner is still active; postpone cleanup.' }
}

$receiptPath = [IO.Path]::GetFullPath($CompletionReceipt)
$receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($receipt.status -ceq 'PUSHED_AND_REMOTE_VERIFIED') {
    if ($receipt.commit -cnotmatch '^[0-9a-f]{40}$' -or
        $receipt.branch -cnotmatch '^docs/[A-Za-z0-9_.-]+$' -or
        $receipt.hardware_diff_from_base_empty -ne $true) {
        throw 'Documentation completion receipt is incomplete'
    }
    $remote = @(& git -C $root ls-remote --heads origin ('refs/heads/' + $receipt.branch))
    if ($LASTEXITCODE -ne 0 -or $remote.Count -ne 1 -or
        ($remote[0] -split '\s+')[0] -cne $receipt.commit) {
        throw 'Documentation publication is not confirmed by the remote branch'
    }
    $completed = [DateTimeOffset]::Parse($receipt.verified_utc).UtcDateTime
    $scope = 'DOCUMENTATION_ONLY_HARDWARE_STATUS_UNCHANGED'
} elseif ($receipt.status -ceq 'SOC_CLEAN_DELIVERY_PASS') {
    if (!$receipt.zip_path -or $receipt.zip_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-FileHash -LiteralPath $receipt.zip_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.zip_sha256) {
        throw 'Completed delivery archive does not match its verification receipt'
    }
    $completed = [DateTimeOffset]::Parse($receipt.completed_utc).UtcDateTime
    $scope = 'VERIFIED_DELIVERY'
} else {
    throw 'Cleanup requires a completed documentation publication or full delivery verification, not candidate/software-only/failed status.'
}
Assert-NoBuildOwner

$targets = @()
foreach ($parent in @((Join-Path $root 'build'), (Join-Path $root 'build/cpu80-20261019'))) {
    if (!(Test-Path -LiteralPath $parent -PathType Container)) { continue }
    [void](Assert-PlainPath $parent $root)
    foreach ($directory in Get-ChildItem -LiteralPath $parent -Directory -Filter 'skills-receipt-*') {
        $targets += $directory
    }
}
if ($IncludeLegacySimulationScratch) {
    $scratch = Join-Path $WorkspaceRoot '_tmp'
    if (Test-Path -LiteralPath $scratch -PathType Container) {
        [void](Assert-PlainPath $scratch $WorkspaceRoot)
        $targets += @(Get-ChildItem -LiteralPath $scratch -File -Filter '*.vvp')
    }
}
$files = @()
$selected = @()
foreach ($target in $targets) {
    [void](Assert-PlainPath $target.FullName $WorkspaceRoot)
    $items = @(if ($target.PSIsContainer) { Get-ChildItem -LiteralPath $target.FullName -Recurse -Force } else { $target })
    if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Linked content inside cleanup candidate'
    }
    $regular = @($items | Where-Object { !$_.PSIsContainer })
    if (!$regular.Count -or @($items + @($target) | Where-Object { $_.LastWriteTimeUtc -gt $completed }).Count) { continue }
    $tracked = @(& git -C $WorkspaceRoot ls-files -- $target.FullName)
    if ($LASTEXITCODE -ne 0 -or $tracked.Count) { throw 'Cleanup candidate contains workspace-tracked files' }
    if ($target.FullName.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        $tracked = @(& git -C $root ls-files -- $target.FullName)
        if ($LASTEXITCODE -ne 0 -or $tracked.Count) { throw 'Cleanup candidate contains project-tracked files' }
    }
    $selected += $target.FullName
    foreach ($file in $regular) {
        $files += [pscustomobject][ordered]@{
            path=Assert-PlainPath $file.FullName $WorkspaceRoot
            relative=$file.FullName.Substring($WorkspaceRoot.Length + 1).Replace('\','/')
            bytes=$file.Length
            sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$record = [ordered]@{
    schema=1;status='CLEANUP_PLAN';created_utc=[DateTime]::UtcNow.ToString('o')
    completion_receipt=$receiptPath;completion_receipt_sha256=(Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
    scope=$scope;project_root=$root;workspace_root=$WorkspaceRoot
    targets=$selected;file_count=$files.Count;bytes=($files | Measure-Object -Property bytes -Sum).Sum;files=$files
    protected='All tracked files, sources, user data/models, boot files, Git worktrees, native PDS databases, frozen candidates and validation evidence.'
}
$store = Join-Path $root 'build/directory-maintenance'
[void](Assert-PlainPath $store $root)
[void](New-Item -ItemType Directory -Path $store -Force)
[IO.File]::WriteAllText((Join-Path $store 'cleanup-plan.json'), ($record | ConvertTo-Json -Depth 12) + "`n", $utf8)
if ($Action -ceq 'Plan' -or !$files.Count) {
    Write-Output "CLEANUP_PLAN files=$($files.Count) bytes=$($record.bytes) targets=$($selected.Count)"
    return
}
Assert-NoBuildOwner
$id = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$archiveDir = Assert-PlainPath (Join-Path $WorkspaceRoot 'archive/directory-maintenance') $WorkspaceRoot
[void](New-Item -ItemType Directory -Path $archiveDir -Force)
$zipPath = Join-Path $archiveDir ($id + '.zip')
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $files) {
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.path,
            $file.relative, [IO.Compression.CompressionLevel]::Optimal)
    }
    $entry = $zip.CreateEntry('CLEANUP_MANIFEST.json')
    $writer = [IO.StreamWriter]::new($entry.Open(), $utf8)
    try { $writer.Write(($record | ConvertTo-Json -Depth 12)) } finally { $writer.Dispose() }
} finally { $zip.Dispose() }
$zip = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    foreach ($file in $files) {
        $entry = $zip.GetEntry($file.relative)
        if (!$entry -or $entry.Length -ne $file.bytes) { throw 'Cleanup archive inventory mismatch; originals retained' }
        $stream = $entry.Open(); $hash = [Security.Cryptography.SHA256]::Create()
        try { $digest = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose(); $hash.Dispose() }
        if ($digest -cne $file.sha256) { throw 'Cleanup archive hash mismatch; originals retained' }
    }
} finally { $zip.Dispose() }
foreach ($file in $files) {
    [void](Assert-PlainPath $file.path $WorkspaceRoot)
    if ((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.sha256) {
        throw 'Cleanup input changed; originals retained'
    }
}
$record.status='ARCHIVED_VERIFIED_READY_TO_REMOVE'
$record.archive_path=$zipPath
$record.archive_sha256=(Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$resultPath = Join-Path $root ('docs/validation/directory-maintenance/' + $id + '.json')
[void](Assert-PlainPath $resultPath $root)
[void](New-Item -ItemType Directory -Path (Split-Path -Parent $resultPath) -Force)
[IO.File]::WriteAllText($resultPath, ($record | ConvertTo-Json -Depth 12) + "`n", $utf8)
foreach ($file in $files) { Remove-Item -LiteralPath $file.path -Force }
foreach ($target in $selected) {
    if (!(Test-Path -LiteralPath $target -PathType Container)) { continue }
    $directories = @(Get-ChildItem -LiteralPath $target -Directory -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $directories) {
        [void](Assert-PlainPath $directory.FullName $WorkspaceRoot)
        if (!(Get-ChildItem -LiteralPath $directory.FullName -Force)) { Remove-Item -LiteralPath $directory.FullName -Force }
    }
    [void](Assert-PlainPath $target $WorkspaceRoot)
    if (!(Get-ChildItem -LiteralPath $target -Force)) { Remove-Item -LiteralPath $target -Force }
}
$record.status='ARCHIVED_VERIFIED_REMOVED_DISPOSABLE_OUTPUT'
$record.completed_utc=[DateTime]::UtcNow.ToString('o')
[IO.File]::WriteAllText($resultPath, ($record | ConvertTo-Json -Depth 12) + "`n", $utf8)
Write-Output "CLEANUP_DONE files=$($files.Count) bytes=$($record.bytes) archive=$zipPath report=$resultPath"
