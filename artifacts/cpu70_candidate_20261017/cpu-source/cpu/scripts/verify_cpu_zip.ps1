param([Parameter(Mandatory=$true)][string]$ZipPath)
$ErrorActionPreference = 'Stop'
function Assert-CanonicalZipPath([string]$Name) {
    if (!$Name -or $Name -match '[\\:"<>|?*]' -or [IO.Path]::IsPathRooted($Name) -or
        @($Name.Split('/') | Where-Object { !$_ -or $_ -in @('.','..') -or $_ -match '[ .]$' }).Count) {
        throw "Noncanonical CPU ZIP entry: $Name"
    }
}
Add-Type -AssemblyName System.IO.Compression
$stream = [IO.File]::OpenRead([IO.Path]::GetFullPath($ZipPath))
try {
    $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Read, $false)
    try {
        $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $archive.Entries) {
            Assert-CanonicalZipPath $entry.FullName
            if (!$entry.FullName.StartsWith('CPU/') -or $entry.FullName -match '\\|(^|/)\.\.?(/|$)' -or !$names.Add($entry.FullName)) {
                throw "Noncanonical or duplicate CPU ZIP entry: $($entry.FullName)"
            }
        }
        $manifestEntry = $archive.GetEntry('CPU/cpu/handoff/package-manifest.json')
        if (!$manifestEntry) { throw 'CPU ZIP has no package manifest' }
        $reader = [IO.StreamReader]::new($manifestEntry.Open(), [Text.Encoding]::UTF8)
        try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        if ($manifest.schema_version -notin @(2,3) -or $manifest.root_scope -cne 'src_repository') { throw 'Unsupported CPU ZIP manifest' }
        if ($archive.Entries.Count -ne @($manifest.files).Count + 1) { throw 'CPU ZIP contains missing/unlisted entries' }
        $listed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($record in $manifest.files) {
            Assert-CanonicalZipPath $record.path
            if (!$listed.Add([string]$record.path)) { throw 'Duplicate CPU ZIP manifest input' }
            $entry = $archive.GetEntry('CPU/' + $record.path)
            if (!$entry -or $entry.Length -ne $record.bytes) { throw "CPU ZIP missing or wrong length: $($record.path)" }
            $inputStream = $entry.Open(); $sha = [Security.Cryptography.SHA256]::Create()
            try { $actual = [BitConverter]::ToString($sha.ComputeHash($inputStream)).Replace('-','') }
            finally { $sha.Dispose(); $inputStream.Dispose() }
            if ($actual -ine $record.sha256) { throw "CPU ZIP SHA256 mismatch: $($record.path)" }
        }
        Write-Output "CPU_ZIP_CONTENT_PASS files=$($listed.Count) version=$($manifest.release_version)"
    } finally { $archive.Dispose() }
} finally { $stream.Dispose() }
