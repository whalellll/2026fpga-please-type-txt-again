param([string]$ReportPath = '', [string]$PythonPath = 'python.exe')
$ErrorActionPreference = 'Stop'
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$fixture = Join-Path $tempBase ('delivery-policy-' + [guid]::NewGuid().ToString('N'))
$utf8 = [Text.UTF8Encoding]::new($false)
$checks = [Collections.Generic.List[object]]::new()
$policyError = 'SOC_V6_5_REQUIRES_BOARD_RELEASE:*'
$entryPoints = @('create_delivery.ps1','verify_delivery.ps1','verify_delivery_evidence.ps1')
$sourceHashes = [ordered]@{}
function Write-Fixture([string]$Relative, [string]$Text) {
    $path = Join-Path $fixture $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, $Text, $utf8)
}
function Invoke-EntryCase([string]$Entry, [string]$Version, [string]$Mode,
    [string]$Manifest, [string]$Expected, [string]$ZipPath = '') {
    Write-Fixture 'VERSION' $Version
    $arguments = @{CoremarkEvidenceMode=$Mode;ReleaseManifest=$Manifest;PythonPath=$PythonPath}
    if ($Entry -ceq 'create_delivery.ps1') {
        $arguments.OutputZip = Join-Path $fixture 'never-created.zip'
    } elseif ($Entry -ceq 'verify_delivery.ps1') {
        $arguments.ZipPath = if ($ZipPath) { $ZipPath } else { Join-Path $fixture 'missing.zip' }
    } else { $arguments.Root = $fixture }
    $failure = ''
    try { & (Join-Path $fixture "scripts/$Entry") @arguments | Out-Null }
    catch { $failure = $_.Exception.Message }
    if ($failure -notlike $Expected) {
        throw "${Entry}/${Version}/${Mode}: expected '$Expected', got '$failure'"
    }
    if (Test-Path -LiteralPath (Join-Path $fixture 'never-created.zip')) {
        throw 'Policy fixture unexpectedly created a release ZIP'
    }
    $checks.Add([ordered]@{entry=$Entry;version=$Version;mode=$Mode;
        manifest_supplied=![string]::IsNullOrWhiteSpace($Manifest);
        expected=$Expected;observed=$failure;status='PASS'})
}
try {
    New-Item -ItemType Directory -Path (Join-Path $fixture 'scripts') -Force | Out-Null
    foreach ($name in @($entryPoints) + 'project_files.ps1') {
        $source = Join-Path $PSScriptRoot $name
        $target = Join-Path $fixture "scripts/$name"
        Copy-Item -LiteralPath $source -Destination $target
        $sourceHashes[$name] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sourceHashes[$name]) {
            throw "Fixture changed the real entry point: $name"
        }
    }
    # Stop at the first downstream gate. These sentinels do not simulate an
    # accepted release; the tests exercise the byte-identical entry scripts.
    Write-Fixture 'scripts/audit_project.ps1' 'param([string]$Root,[switch]$CheckHashes) throw "SYNTHETIC_POLICY_NEXT_AUDIT"'
    # Index refresh precedes audit in the real entry. This policy fixture checks
    # mode rejection and stops at audit; it does not claim an index or release pass.
    Write-Fixture 'scripts/update_project_index.py' 'print("SYNTHETIC_POLICY_INDEX_REFRESH_ONLY")'
    Write-Fixture 'scripts/riscv_toolchain.ps1' 'function Get-CpuToolchain { param([string]$ToolchainBin) return @{Bin="SYNTHETIC_NO_COMPILER"} }'
    Write-Fixture 'config/clocks.json' '{"cpu_divisor":15}'
    New-Item -ItemType Directory -Path (Join-Path $fixture 'docs/validation/frequency-search') -Force | Out-Null
    foreach ($entry in $entryPoints) {
        foreach ($mode in @('Production','ShortPilot','BoardRelease')) {
            Invoke-EntryCase $entry '6.5' $mode '' $policyError
        }
        Invoke-EntryCase $entry '6.5' 'BoardRelease' '   ' $policyError
        foreach ($mode in @('Production','ShortPilot')) {
            Invoke-EntryCase $entry '6.5' $mode 'docs/validation/synthetic-release.json' $policyError
        }
        $nextGate = switch ($entry) {
            'create_delivery.ps1' { 'SYNTHETIC_POLICY_NEXT_AUDIT' }
            'verify_delivery.ps1' { 'Missing archive:*' }
            'verify_delivery_evidence.ps1' { 'Delivery requires a verified PASS frequency archive*' }
        }
        Invoke-EntryCase $entry '6.5' 'BoardRelease' 'docs/validation/synthetic-release.json' $nextGate
        foreach ($mode in @('Production','ShortPilot')) {
            Invoke-EntryCase $entry '6.1' $mode '' $nextGate
        }
    }
    # A historical invoking tree cannot admit a V6.5 archive in a legacy mode.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipPath = Join-Path $fixture 'synthetic-v6.5.zip'
    $archive = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $entry = $archive.CreateEntry('SOC/VERSION')
        $writer = [IO.StreamWriter]::new($entry.Open(), $utf8)
        try { $writer.Write('6.5') } finally { $writer.Dispose() }
    } finally { $archive.Dispose() }
    foreach ($mode in @('Production','ShortPilot','BoardRelease')) {
        Invoke-EntryCase 'verify_delivery.ps1' '6.1' $mode '' $policyError $zipPath
    }
    foreach ($mode in @('Production','ShortPilot')) {
        Invoke-EntryCase 'verify_delivery.ps1' '6.1' $mode 'docs/validation/synthetic-release.json' $policyError $zipPath
    }
    $record = [ordered]@{schema=1;status='DELIVERY_MODE_POLICY_PASS';synthetic_only=$true;
        hardware_operations=0;release_acceptance_claimed=$false;checks=$checks.ToArray();
        source_sha256=$sourceHashes}
    if ($ReportPath) {
        if (Test-Path -LiteralPath $ReportPath) { throw "Refusing to overwrite $ReportPath" }
        [IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath), ($record | ConvertTo-Json -Depth 6), $utf8)
    }
    Write-Output "DELIVERY_MODE_POLICY_PASS checks=$($checks.Count) real_entry_points=3 NO_COMPILER_NO_SIMULATION_NO_PDS_NO_JTAG"
} finally {
    if (Test-Path -LiteralPath $fixture) {
        $resolved = (Get-Item -LiteralPath $fixture -Force).FullName
        if (!$resolved.StartsWith($tempBase + '\delivery-policy-', [StringComparison]::OrdinalIgnoreCase) -or
            ((Get-Item -LiteralPath $fixture -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            @(Get-ChildItem -LiteralPath $fixture -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
            throw 'Unsafe delivery-policy fixture cleanup'
        }
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}
