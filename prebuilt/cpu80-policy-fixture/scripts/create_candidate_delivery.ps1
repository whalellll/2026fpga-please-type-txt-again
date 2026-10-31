param(
    [Parameter(Mandatory=$true)][string[]]$Incomplete,
    [string[]]$IncludeArtifact = @(),
    [string[]]$IncludeSource = @(),
    [string]$OutputZip,
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe'
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'project_files.ps1')
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
& (Join-Path $PSScriptRoot 'invoke_project_skills.ps1') -Arguments @('verify-delivery', '--package', $root)
if (!$Incomplete.Count -or @($Incomplete | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count) {
    throw 'Candidate delivery must explicitly state incomplete acceptance items'
}
if (!$OutputZip) { $OutputZip = Join-Path (Split-Path -Parent $root) "SOC_linux_V${script:ProjectVersion}_candidate.zip" }
$OutputZip = [IO.Path]::GetFullPath($OutputZip)
if ([IO.Path]::GetExtension($OutputZip) -ine '.zip' -or
    [IO.Path]::GetFileName($OutputZip) -ieq "SOC_linux_V$script:ProjectVersion.zip" -or (Test-Path -LiteralPath $OutputZip)) {
    throw 'Use a new candidate ZIP path, distinct from the formal release filename'
}
# Source inventory only by default. Existing artifacts may belong to an older
# CPU/frequency; a candidate must never silently publish them as its hardware.
$files = @(Get-ProjectFiles $root -SourceOnly)
foreach ($relative in $IncludeSource) {
    if ($relative -like 'artifacts/*' -or $relative -match '(^|/)(\.git|build|workspace|\u6570\u636e\u96c6)(/|$)') {
        throw 'IncludeSource must name reviewed source outside artifacts, private data and generated work directories'
    }
    [void](Get-FpgaSafePath $root $relative)
    $files += $relative
}
foreach ($relative in $IncludeArtifact) {
    if ($relative -notlike 'artifacts/*') { throw 'IncludeArtifact must name a repository-relative artifacts/ file' }
    [void](Get-FpgaSafePath $root $relative)
    $files += $relative
}
$files = @($files | Sort-Object -Unique)
$hashes = [ordered]@{}
foreach ($relative in $files) {
    $path = Get-FpgaSafePath $root $relative
    $hashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$source = [IO.File]::ReadAllText((Join-Path $root 'rtl/cpu/source.json')) | ConvertFrom-Json
if ($source.sha256 -cne $hashes['rtl/cpu/CoreTop.sv']) { throw 'Candidate CPU RTL differs from its import manifest' }
$record = [ordered]@{
    schema_version = 1; status = 'CANDIDATE_NOT_RELEASE'; release_version = $script:ProjectVersion
    created_utc = [DateTime]::UtcNow.ToString('o'); incomplete_acceptance = @($Incomplete)
    cpu_source_manifest_sha256 = $hashes['rtl/cpu/source.json']; cpu_rtl_sha256 = $hashes['rtl/cpu/CoreTop.sv']
    cpu_implementation_commit = $source.source_reference_commit
    selected_artifacts = @($IncludeArtifact)
    selected_source_extras = @($IncludeSource)
    artifact_scope = 'Explicitly selected reproducibility artifacts only; inclusion does not establish final STA or board acceptance.'
    files_sha256 = $hashes
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$part = $OutputZip + '.' + [guid]::NewGuid().ToString('N') + '.part'
try {
    $zip = [IO.Compression.ZipFile]::Open($part, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($relative in $files) {
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $root $relative),
                ('SOC_CANDIDATE/' + $relative), [IO.Compression.CompressionLevel]::Optimal)
        }
        $entry = $zip.CreateEntry('SOC_CANDIDATE/candidate-delivery.json')
        $writer = [IO.StreamWriter]::new($entry.Open(), [Text.UTF8Encoding]::new($false))
        try { $writer.Write(($record | ConvertTo-Json -Depth 12) + "`n") } finally { $writer.Dispose() }
    } finally { $zip.Dispose() }
    & $PythonPath -B (Join-Path $PSScriptRoot 'verify_candidate_delivery.py') $part
    if ($LASTEXITCODE -ne 0) { throw 'Candidate ZIP content/hash verification failed' }
    Move-Item -LiteralPath $part -Destination $OutputZip
} finally {
    if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force }
}
Write-Output "SOC_CANDIDATE_DELIVERY_NOT_RELEASE path=$OutputZip"
Write-Output ('SHA256: ' + (Get-FileHash -LiteralPath $OutputZip -Algorithm SHA256).Hash.ToLowerInvariant())
