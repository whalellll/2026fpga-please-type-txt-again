param()
$ErrorActionPreference = 'Stop'
$scratchRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../work')).TrimEnd('\')
$temporary = Join-Path $scratchRoot ('package-policy-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [Text.UTF8Encoding]::new($false)

function New-Fixture([string]$Name, [string]$EntryName = 'CPU/README.md',
    [switch]$ChangedBytes, [switch]$ExtraEntry, [switch]$DuplicateEntry) {
    $payload = $utf8.GetBytes('SYNTHETIC ZIP CONTENT FIXTURE; NOT A CPU RELEASE')
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($hasher.ComputeHash($payload)).Replace('-','') }
    finally { $hasher.Dispose() }
    $manifest = [ordered]@{
        schema_version=3; root_scope='src_repository'; release_version='3.5.0'; evidence_mode='candidate'
        files=@([ordered]@{path=$EntryName.Substring(4);sha256=$hash;bytes=$payload.Length})
    }
    $path = Join-Path $temporary ($Name + '.zip')
    $zip = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $stream = $zip.CreateEntry($EntryName).Open()
        try {
            if ($ChangedBytes) { $payload[0] = [byte][char]'X' }
            $stream.Write($payload, 0, $payload.Length)
        } finally { $stream.Dispose() }
        $writer = [IO.StreamWriter]::new($zip.CreateEntry('CPU/cpu/handoff/package-manifest.json').Open(), $utf8)
        try { $writer.Write(($manifest | ConvertTo-Json -Depth 8)) } finally { $writer.Dispose() }
        if ($ExtraEntry) { [void]$zip.CreateEntry('CPU/extra.txt') }
        if ($DuplicateEntry) { [void]$zip.CreateEntry($EntryName) }
    } finally { $zip.Dispose() }
    return $path
}

try {
    $valid = New-Fixture 'valid'
    $output = & (Join-Path $PSScriptRoot 'verify_cpu_zip.ps1') -ZipPath $valid
    if (($output -join "`n") -notmatch 'CPU_ZIP_CONTENT_PASS') { throw 'Valid content fixture did not pass' }
    $cases = @(
        @{name='changed_bytes';path=(New-Fixture 'changed_bytes' -ChangedBytes);error='SHA256 mismatch'},
        @{name='unlisted_entry';path=(New-Fixture 'unlisted_entry' -ExtraEntry);error='missing/unlisted entries'},
        @{name='duplicate_entry';path=(New-Fixture 'duplicate_entry' -DuplicateEntry);error='duplicate CPU ZIP entry'},
        @{name='traversal';path=(New-Fixture 'traversal' -EntryName 'CPU/../escape.txt');error='Noncanonical'},
        @{name='drive_syntax';path=(New-Fixture 'drive_syntax' -EntryName 'CPU/C:escape.txt');error='Noncanonical'},
        @{name='trailing_dot';path=(New-Fixture 'trailing_dot' -EntryName 'CPU/README.md.');error='Noncanonical'},
        @{name='trailing_space';path=(New-Fixture 'trailing_space' -EntryName 'CPU/README.md ');error='Noncanonical'},
        @{name='empty_component';path=(New-Fixture 'empty_component' -EntryName 'CPU//README.md');error='Noncanonical'}
    )
    foreach ($case in $cases) {
        $message = ''
        try { & (Join-Path $PSScriptRoot 'verify_cpu_zip.ps1') -ZipPath $case.path | Out-Null }
        catch { $message = $_.Exception.Message }
        if (!$message.Contains($case.error)) { throw "Unexpected fixture result $($case.name): $message" }
    }
    # A stubbed input-verifier boundary isolates package orchestration. This is
    # deliberately not evidence of real CPU generation or firmware validation.
    # Invoke the real verifier from this checkout with a different -Root; only
    # the fixture root's stub may run, never this checkout's generated verifier.
    $package = Join-Path $temporary 'external-package'
    $required = @('README.md','AGENTS.md','VERSION','CHANGELOG.md','.gitattributes','.gitignore',
        'cpu/generated/manifest.json','cpu/generated/core/CoreTop.sv','cpu/generated/sim/CoreTop.sv',
        'cpu/generated/core/emit-config.json','cpu/generated/sim/emit-config.json',
        'cpu/handoff/NEW_COMPUTER_GUIDE.md','cpu/scripts/newpc.ps1','cpu/scripts/verify_cpu_package.ps1',
        'cpu/scripts/verify_build_inputs.ps1','cpu/coremark_test_soc/pds/coremark_test_soc.pds',
        'cpu/coremark_test_soc/sim/coremark_ima/manifest.json','cpu/coremark_test_soc/sim/coremark_validation/manifest.json')
    foreach ($name in $required) {
        $target = Join-Path $package $name
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        [IO.File]::WriteAllText($target, 'SYNTHETIC PACKAGE ORCHESTRATION FIXTURE', $utf8)
    }
    [IO.File]::WriteAllText((Join-Path $package 'VERSION'), '3.5.0', $utf8)
    $stub = @'
param([switch]$GeneratedCpu, [string]$FirmwareDirectory)
$expectedRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if ($GeneratedCpu) {
    Write-Output ('SYNTHETIC_PACKAGE_HELPER_ROOT=' + $expectedRoot)
} elseif (!$FirmwareDirectory.StartsWith($expectedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Fixture firmware helper received another root'
}
'@
    [IO.File]::WriteAllText((Join-Path $package 'cpu/scripts/verify_build_inputs.ps1'), $stub, $utf8)
    foreach ($pair in @(@('coremark_ima','performance'),@('coremark_validation','validation'))) {
        $firmware = @{run_mode=$pair[1];iterations=10;evidence_class='calibration';compiler_version='16.2.0';optimization='-O2'}
        [IO.File]::WriteAllText((Join-Path $package ('cpu/coremark_test_soc/sim/' + $pair[0] + '/manifest.json')),
            ($firmware | ConvertTo-Json), $utf8)
    }
    $entries = @(foreach ($name in $required) {
        $file = Get-Item -LiteralPath (Join-Path $package $name)
        @{path=$name;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash;bytes=$file.Length}
    })
    $record = @{schema_version=3;root_scope='src_repository';release_version='3.5.0';evidence_mode='candidate';release_manifest=$null;files=$entries}
    $recordPath = Join-Path $package 'cpu/handoff/package-manifest.json'
    [IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json -Depth 8), $utf8)
    $verified = @(& (Join-Path $PSScriptRoot 'verify_cpu_package.ps1') -Root $package)
    if (($verified -join "`n") -notmatch 'PACKAGE_VERIFY_PASS' -or
        ('SYNTHETIC_PACKAGE_HELPER_ROOT=' + $package) -notin $verified) {
        throw 'External -Root was not verified using its own input verifier'
    }
    $extra = Join-Path $package 'unlisted.txt'
    [IO.File]::WriteAllText($extra, 'unlisted fixture', $utf8)
    $message = ''
    try { & (Join-Path $PSScriptRoot 'verify_cpu_package.ps1') -Root $package | Out-Null }
    catch { $message = $_.Exception.Message }
    if (!$message.Contains('missing or unlisted files')) { throw "Extra package file was not rejected: $message" }
    Remove-Item -LiteralPath $extra
    $record.files[0].path = 'cpu/../README.md'
    [IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json -Depth 8), $utf8)
    $message = ''
    try { & (Join-Path $PSScriptRoot 'verify_cpu_package.ps1') -Root $package | Out-Null }
    catch { $message = $_.Exception.Message }
    if (!$message.Contains('Noncanonical package path')) { throw "Traversal manifest path was not rejected: $message" }
    Write-Output 'CPU_PACKAGE_POLICY_PASS zip_positive=1 zip_negative=8 external_root_positive=1 directory_negative=2 synthetic_only=true'
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    if (!$resolved.StartsWith($scratchRoot + '\package-policy-', [StringComparison]::OrdinalIgnoreCase) -or
        ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        @(Get-ChildItem -LiteralPath $resolved -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        }).Count) { throw 'Refusing unsafe temporary package fixture cleanup' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
