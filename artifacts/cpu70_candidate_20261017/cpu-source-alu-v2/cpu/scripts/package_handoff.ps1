param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../handoff-packages'),
    [switch]$Candidate,
    [string]$ReleaseManifest = '',
    [string]$PythonPath = 'python',
    [string]$HostGccPath = 'gcc'
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
if ($outputRoot.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $outputRoot -eq $root) {
    throw 'OutputDirectory must be outside the project to avoid recursive packaging.'
}
$repo = Split-Path $root -Parent
$releaseVersion = [IO.File]::ReadAllText((Join-Path $repo 'VERSION')).Trim()
if ($releaseVersion -cnotmatch '^\d+\.\d+\.\d+$') { throw "Invalid CPU version: $releaseVersion" }
$displayVersion = ([regex]::Match($releaseVersion, '^\d+\.\d+')).Value
$legacy = $releaseVersion -ceq '3.1.0' -and !$Candidate -and !$ReleaseManifest
$label = "CPU_V${displayVersion}_source"
if ($Candidate) { $label = "CPU_V${displayVersion}_candidate_source" }
if ($Candidate -and $ReleaseManifest) { throw 'Candidate packaging must not assert a formal release manifest' }
if (!$legacy -and !$Candidate -and !$ReleaseManifest) { throw 'Formal CPU package requires an explicit current integrated-board ReleaseManifest; use -Candidate for unaccepted work' }
$releaseRelative = $null
if ($ReleaseManifest) {
    $releaseFull = [IO.Path]::GetFullPath($ReleaseManifest)
    if (!$releaseFull.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'ReleaseManifest must be inside this source repository' }
    $releaseRelative = $releaseFull.Substring($repo.Length + 1).Replace('\','/')
}
& (Join-Path $PSScriptRoot 'verify_build_inputs.ps1') -GeneratedCpu
$stageName = 'cpu_delivery_' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$stage = Join-Path $outputRoot "$stageName/CPU"
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Write-Output 'Package: expected under 1 minute; Ctrl+C stops it. Copies files only; no tools or personal profiles.'
# Use the current Git input inventory so ignored PDS databases/ROM copies,
# sbt targets and work experiments can never leak into the source package.
function Get-GitInputInventory([string]$Pathspec) {
    # Git emits unquoted paths as UTF-8; hidden Windows PowerShell may use CP936.
    $savedConsoleEncoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        $paths = @(& git -C $repo -c core.quotepath=false ls-files --cached --others --exclude-standard -- $Pathspec)
        if ($LASTEXITCODE -ne 0) { throw "Git input inventory failed: $Pathspec" }
        return $paths
    } finally {
        [Console]::OutputEncoding = $savedConsoleEncoding
    }
}
foreach ($name in @('README.md', 'AGENTS.md', '.gitattributes', '.gitignore', 'VERSION', 'CHANGELOG.md')) {
    $source = Join-Path $repo $name
    $rootEntry = @(Get-GitInputInventory $name)
    if ($name -notin $rootEntry -or !(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing Git input inventory entry: $name" }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked repository entry: $name" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stage $name)
}
$inventory = @(Get-GitInputInventory 'cpu')
if (!$inventory.Count) { throw 'Packaging requires the src Git checkout and a nonempty input inventory' }
foreach ($entry in $inventory | Sort-Object -Unique) {
    if (!$entry.StartsWith('cpu/')) { throw "Unexpected package path: $entry" }
    $relative = $entry.Substring('cpu/'.Length)
    if ($relative -eq 'handoff/package-manifest.json') { continue }
    $source = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (!$source.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Package path escaped root: $relative" }
    # Stage intended deletions first: Git's cached inventory then omits them.
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing package input: $entry. Stage intended deletions before packaging." }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked package input: $relative" }
    $dest = Join-Path $stage $entry
    New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $dest
}
$entries = @(Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($stage.Length + 1).Replace('\','/')
    if ($relative -ne 'cpu/handoff/package-manifest.json') {
        [ordered]@{ path = $relative; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash; bytes = $_.Length }
    }
})
$manifest = [ordered]@{
    schema_version = $(if ($legacy) { 2 } else { 3 }); root_scope = 'src_repository'
    createdUtc = [DateTime]::UtcNow.ToString('o')
    release_version = $releaseVersion
    profile = "CPU V$displayVersion source handoff; excludes machine tools and caches"
    files = $entries
}
if (!$legacy) {
    $manifest.evidence_mode = $(if ($Candidate) { 'candidate' } else { 'integrated_board' })
    $manifest.release_manifest = $releaseRelative
}
$manifestJson = ($manifest | ConvertTo-Json -Depth 5).Replace("`r`n", "`n") + "`n"
[IO.File]::WriteAllText((Join-Path $stage 'cpu/handoff/package-manifest.json'),
    $manifestJson, [Text.UTF8Encoding]::new($false))
if (!$legacy) {
    & (Join-Path $stage 'cpu/scripts/verify_cpu_package.ps1') -Root $stage -PythonPath $PythonPath -HostGccPath $HostGccPath
}
$zip = Join-Path $outputRoot "$label.zip"
if (Test-Path -LiteralPath $zip) { throw "Release ZIP already exists: $zip" }
# PowerShell's Compress-Archive on Windows writes backslashes into ZIP entry
# names.  Explicit POSIX names keep the same package usable by unzip on Linux.
Add-Type -AssemblyName System.IO.Compression
$zipStream = [IO.File]::Open($zip, [IO.FileMode]::CreateNew)
try {
    $archive = [IO.Compression.ZipArchive]::new($zipStream, [IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName) {
            $entryName = 'CPU/' + $file.FullName.Substring($stage.Length + 1).Replace('\', '/')
            $entry = $archive.CreateEntry($entryName, [IO.Compression.CompressionLevel]::Optimal)
            $inputStream = [IO.File]::OpenRead($file.FullName)
            try {
                $entryStream = $entry.Open()
                try { $inputStream.CopyTo($entryStream) } finally { $entryStream.Dispose() }
            } finally { $inputStream.Dispose() }
        }
    } finally { $archive.Dispose() }
} finally { $zipStream.Dispose() }
& (Join-Path $PSScriptRoot 'verify_cpu_zip.ps1') -ZipPath $zip
$hash = Get-FileHash -LiteralPath $zip -Algorithm SHA256
"$($hash.Hash)  $([IO.Path]::GetFileName($zip))" | Set-Content -LiteralPath "$zip.sha256.txt" -Encoding ascii
Write-Output "ZIP: $zip"
Write-Output "SHA256: $($hash.Hash)"
Write-Output "FILES: $($entries.Count)"
