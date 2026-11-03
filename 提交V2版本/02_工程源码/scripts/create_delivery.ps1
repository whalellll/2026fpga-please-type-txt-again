param(
    [string]$OutputZip,
    [switch]$Force,
    [ValidateSet('Production','ShortPilot','BoardRelease')][string]$CoremarkEvidenceMode = 'Production',
    [string]$ReleaseManifest,
    [string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
    [string]$PublicationReceipt = '',
    [string]$CpuRepository = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ($CoremarkEvidenceMode -ceq 'BoardRelease' -and $ReleaseManifest) {
    $selected = Join-Path $root $ReleaseManifest
    if (Test-Path -LiteralPath $selected -PathType Leaf) {
        $profile = Get-Content -LiteralPath $selected -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($profile.schema -ceq 'PDS25_CPU120_ZBC_FC1_BOARD_RELEASE_V1') {
            if (!$PublicationReceipt -or !$CpuRepository -or !$OutputZip) { throw 'CPU120 requires explicit publication receipt, CPU repository and output ZIP.' }
            & $PythonPath -B (Join-Path $PSScriptRoot 'create_cpu120_zbc_delivery.py') --root $root --output $OutputZip --publication $PublicationReceipt --cpu-repository $CpuRepository --host-gcc $HostGccPath
            if ($LASTEXITCODE -ne 0) { throw 'CPU120 accepted-source/native/board/skills/index packaging failed.' }
            return
        }
        if ($profile.schema -ceq 'PDS25_CPU120_BOARD_RELEASE_V1') {
            if (!$PublicationReceipt -or !$CpuRepository -or !$OutputZip) { throw 'CPU120 requires explicit publication receipt, CPU repository and output ZIP.' }
            & $PythonPath -B (Join-Path $PSScriptRoot 'create_cpu120_delivery.py') --root $root --output $OutputZip --publication $PublicationReceipt --cpu-repository $CpuRepository --host-gcc $HostGccPath
            if ($LASTEXITCODE -ne 0) { throw 'CPU120 accepted-source/native/board/skills/index packaging failed.' }
            return
        }
    }
}
. (Join-Path $PSScriptRoot 'project_files.ps1')
if ($script:ProjectVersion -ceq '6.5' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V6_5_REQUIRES_BOARD_RELEASE: V6.5 formal delivery requires BoardRelease and an explicit -ReleaseManifest; incomplete candidates use create_candidate_delivery.ps1.'
}
if ($script:ProjectVersion -ceq '2.1' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V2_1_REQUIRES_BOARD_RELEASE: V2.1 formal delivery requires board-only CoreMark evidence and an explicit -ReleaseManifest.'
}
if (!$OutputZip) { $OutputZip = Join-Path (Split-Path -Parent $root) "SOC_linux_V$script:ProjectVersion.zip" }
$OutputZip = [IO.Path]::GetFullPath($OutputZip)
if ([IO.Path]::GetExtension($OutputZip) -ine '.zip') { throw 'Delivery output must be a .zip file' }
if ((Test-Path -LiteralPath $OutputZip) -and !$Force) { throw "Archive already exists; choose another -OutputZip or use -Force: $OutputZip" }
& $PythonPath -B (Join-Path $PSScriptRoot 'update_project_index.py') --project-root $root
if ($LASTEXITCODE -ne 0) { throw 'Refresh the project directory index before packaging' }
& (Join-Path $PSScriptRoot 'audit_project.ps1') -Root $root
& (Join-Path $PSScriptRoot 'invoke_project_skills.ps1') -Arguments @('verify-delivery', '--package', $root)
& (Join-Path $PSScriptRoot 'verify_delivery_evidence.ps1') -Root $root `
    -CoremarkEvidenceMode $CoremarkEvidenceMode -ReleaseManifest $ReleaseManifest -PythonPath $PythonPath -HostGccPath $HostGccPath
Write-ProjectHashes $root
& (Join-Path $PSScriptRoot 'audit_project.ps1') -Root $root -CheckHashes
$files = @(Get-ProjectFiles $root) + 'SHA256SUMS.txt'
$part = $OutputZip + '.' + [guid]::NewGuid().ToString('N') + '.part'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
try {
    $archive = [IO.Compression.ZipFile]::Open($part, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($relative in $files | Sort-Object) {
            $entry = $archive.CreateEntry("SOC/$relative", [IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = [DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
            $destination = $entry.Open()
            $source = [IO.File]::OpenRead((Join-Path $root $relative))
            try { $source.CopyTo($destination) } finally { $source.Dispose(); $destination.Dispose() }
        }
    } finally { $archive.Dispose() }
    Move-Item -LiteralPath $part -Destination $OutputZip -Force:$Force
} finally { if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force } }
Write-Output "Delivery: $OutputZip"
Write-Output ('SHA256: ' + (Get-FileHash -Algorithm SHA256 -LiteralPath $OutputZip).Hash.ToLowerInvariant())
