param(
    [string]$Root = (Join-Path $PSScriptRoot '../..'),
    [string]$PythonPath = 'python',
    [string]$HostGccPath = 'gcc'
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
if (!(Test-Path -LiteralPath $Root -PathType Container) -or
    ((Get-Item -LiteralPath $Root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'CPU package root must be a regular directory'
}
function Resolve-PackageFile([string]$Name) {
    if (!$Name -or $Name -match '[\\:"<>|?*]' -or [IO.Path]::IsPathRooted($Name) -or
        @($Name.Split('/') | Where-Object { !$_ -or $_ -in @('.','..') -or $_ -match '[ .]$' }).Count) {
        throw "Noncanonical package path: $Name"
    }
    $path = [IO.Path]::GetFullPath((Join-Path $Root $Name))
    if (!$path.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Package path escapes root' }
    $cursor = $path
    while ($cursor -ne $Root) {
        $item = Get-Item -LiteralPath $cursor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked package input: $Name" }
        $cursor = Split-Path $cursor -Parent
    }
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing package file: $Name" }
    return $path
}
$manifest = Get-Content -LiteralPath (Resolve-PackageFile 'cpu/handoff/package-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$version = [IO.File]::ReadAllText((Resolve-PackageFile 'VERSION')).Trim()
if ($manifest.schema_version -ne 3 -or $manifest.root_scope -cne 'src_repository' -or
    $manifest.release_version -cne $version -or $manifest.evidence_mode -cnotin @('candidate','integrated_board')) {
    throw 'Invalid schema-3 CPU package/version/evidence contract'
}
$listed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $manifest.files) {
    if ($entry.path -ieq 'cpu/handoff/package-manifest.json') { throw 'The package manifest cannot include itself in its input inventory' }
    if (!$listed.Add([string]$entry.path)) { throw 'Duplicate package entry' }
    $path = Resolve-PackageFile $entry.path
    if ($entry.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $entry.sha256 -or
        (Get-Item -LiteralPath $path).Length -ne $entry.bytes) { throw "Package bytes changed: $($entry.path)" }
}
foreach ($required in @('README.md','AGENTS.md','VERSION','CHANGELOG.md','.gitattributes','.gitignore',
    'cpu/generated/manifest.json','cpu/generated/core/CoreTop.sv','cpu/generated/sim/CoreTop.sv',
    'cpu/generated/core/emit-config.json','cpu/generated/sim/emit-config.json',
    'cpu/handoff/NEW_COMPUTER_GUIDE.md','cpu/scripts/newpc.ps1','cpu/scripts/verify_cpu_package.ps1','cpu/scripts/verify_build_inputs.ps1',
    'cpu/coremark_test_soc/pds/coremark_test_soc.pds',
    'cpu/coremark_test_soc/sim/coremark_ima/manifest.json','cpu/coremark_test_soc/sim/coremark_validation/manifest.json')) {
    if (!$listed.Contains($required)) { throw "Missing package inventory input: $required" }
}
$nodes = @(Get-ChildItem -LiteralPath $Root -Recurse -Force)
if (@($nodes | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Package contains an unlisted or linked filesystem entry'
}
$actual = @($nodes | Where-Object { !$_.PSIsContainer } | ForEach-Object {
    $_.FullName.Substring($Root.Length + 1).Replace('\','/')
})
$expected = @($manifest.files | ForEach-Object { $_.path }) + 'cpu/handoff/package-manifest.json'
if (@(Compare-Object ($actual | Sort-Object) ($expected | Sort-Object)).Count) {
    throw 'Package directory contains missing or unlisted files'
}
$inputVerifier = Resolve-PackageFile 'cpu/scripts/verify_build_inputs.ps1'
& $inputVerifier -GeneratedCpu
foreach ($mode in @(@('coremark_ima','performance'), @('coremark_validation','validation'))) {
    $firmware = Join-Path $Root ('cpu/coremark_test_soc/sim/' + $mode[0])
    & $inputVerifier -FirmwareDirectory $firmware
    $input = Get-Content -LiteralPath (Join-Path $firmware 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($input.run_mode -cne $mode[1] -or $input.iterations -ne 10 -or
        $input.evidence_class -cne 'calibration' -or $input.compiler_version -cne '16.2.0' -or $input.optimization -cne '-O2') {
        throw 'Current CPU package must provide GCC16.2/O2 ten-iteration short RTL inputs; formal performance belongs to the integrated board'
    }
}
if ($manifest.evidence_mode -ceq 'integrated_board') {
    $releasePath = Resolve-PackageFile $manifest.release_manifest
    if (!$listed.Contains($manifest.release_manifest)) { throw 'Unlisted CPU release manifest' }
    $release = Get-Content -LiteralPath $releasePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($release.schema -ne 1 -or $release.cpu_version -cne $version -or $release.platform -cne 'performance_soc') {
        throw 'CPU release must identify the current integrated SoC platform and version'
    }
    $receipt = Resolve-PackageFile $release.receipt.path
    if (!$listed.Contains($release.receipt.path) -or
        (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash -ine $release.receipt.sha256) { throw 'CPU board receipt changed or unlisted' }
    $verifier = Resolve-PackageFile $release.verifier
    if (!$listed.Contains($release.verifier)) { throw 'Unlisted board verifier' }
    & $PythonPath -B $verifier --receipt $receipt --cpu-root $Root --host-gcc $HostGccPath
    if ($LASTEXITCODE -ne 0) { throw 'Integrated board release receipt verification failed' }
} elseif ($manifest.release_manifest) { throw 'Candidate package cannot claim a formal release manifest' }
Write-Output "PACKAGE_VERIFY_PASS files=$($listed.Count) version=$version evidence=$($manifest.evidence_mode)"
