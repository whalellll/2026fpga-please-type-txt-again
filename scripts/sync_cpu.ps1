param(
    [string]$SourceRepo = '',
    [switch]$Check,
    [switch]$AllowSupervisorCandidate
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$relativeSource = 'cpu/generated/core/CoreTop.sv'
$relativeSourceConfig = 'cpu/generated/core/emit-config.json'
$relativeMeminit = 'cpu/scripts/meminit'
$relativeTarget = 'rtl/cpu/CoreTop.sv'
$relativeTargetConfig = 'rtl/cpu/emit-config.json'
$target = Join-Path $root $relativeTarget
$targetConfig = Join-Path $root $relativeTargetConfig
$manifestPath = Join-Path $root 'rtl/cpu/source.json'
$meminitNames = @('zero_1024.hex','zero_2048.hex','zero_4096.hex')
function Assert-GeneratedSource([string]$Repository) {
    $verify = Join-Path $Repository 'cpu/scripts/verify_build_inputs.ps1'
    if (!(Test-Path -LiteralPath $verify -PathType Leaf)) {
        throw 'Source checkout lacks its generated RTL input verifier; use the complete src repository'
    }
    # Hashing today's Scala beside yesterday's RTL is not evidence of an Emit.
    # The source repository verifies both exports against the recorded inputs.
    & $verify -GeneratedCpu
}
function Get-GeneratorSourceHash([string]$Repository) {
    $inputs = @(Get-ChildItem -LiteralPath (Join-Path $Repository 'cpu/src/main') -Recurse -File)
    $inputs += Get-Item -LiteralPath (Join-Path $Repository 'cpu/build.sbt')
    $inputs += Get-Item -LiteralPath (Join-Path $Repository 'cpu/project/build.properties')
    $inputs += Get-Item -LiteralPath (Join-Path $Repository 'cpu/project/plugins.sbt')
    $rows = @($inputs | Sort-Object FullName | ForEach-Object {
        $_.FullName.Substring($Repository.Length + 1).Replace('\','/') + ' ' +
        (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    })
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($rows -join "`n")))).Replace('-','').ToLowerInvariant()
    } finally { $sha.Dispose() }
}
function Assert-SynthesisConfiguration([string]$Path, [bool]$SupervisorCandidate) {
    $configuration = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if (($configuration.schema_version -isnot [int] -and $configuration.schema_version -isnot [long]) -or
        $configuration.schema_version -ne 1 -or $configuration.isa -cne 'rv32ima_zicsr_zifencei' -or
        $configuration.supervisor -isnot [bool] -or $configuration.supervisor -ne $SupervisorCandidate -or
        $configuration.mode.synthesis -isnot [bool] -or !$configuration.mode.synthesis -or
        $configuration.mode.socProbes -isnot [bool] -or $configuration.mode.socProbes) {
        throw 'CPU emit-config.json must describe the selected RV32IMA synthesis profile without simulation probes; sync the generated CPU again'
    }
    $architectureKeys = @('aluEntries','memEntries','fallbackSets','fallbackHash','rasDepth')
    $names = @($configuration.architecture.PSObject.Properties.Name)
    if ($configuration.architecture -isnot [pscustomobject] -or $names.Count -ne $architectureKeys.Count -or
        @($names | Where-Object { $_ -cnotin $architectureKeys }).Count) {
        throw 'CPU emit configuration is missing its supported architecture parameters'
    }
    foreach ($name in $architectureKeys) {
        $value = $configuration.architecture.$name
        if ($name -eq 'fallbackHash') {
            if ($value -isnot [bool]) { throw 'CPU fallbackHash must be a JSON boolean' }
        } elseif (($value -isnot [int] -and $value -isnot [long]) -or $value -lt 1 -or $value -gt 2147483647) {
            throw "CPU architecture parameter must be a positive JSON integer: $name"
        }
    }
}
if ($Check) {
    if ($SourceRepo) {
        $SourceRepo = [IO.Path]::GetFullPath($SourceRepo).TrimEnd('\','/')
        Assert-GeneratedSource $SourceRepo
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.source_config_path -cne $relativeSourceConfig -or
        $manifest.destination_config_path -cne $relativeTargetConfig -or
        $manifest.config_sha256 -isnot [string] -or $manifest.config_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'CPU source.json lacks the current emit-configuration binding; run sync_cpu.ps1 -SourceRepo again'
    }
    if (!(Test-Path -LiteralPath $targetConfig -PathType Leaf)) { throw 'CPU emit-config.json is missing; sync the generated CPU again' }
    $configHash = (Get-FileHash -LiteralPath $targetConfig -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($configHash -cne $manifest.config_sha256) { throw 'CPU emit configuration hash differs from source.json; sync the generated CPU again' }
    Assert-SynthesisConfiguration $targetConfig ($manifest.supervisor_candidate -eq $true)
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $manifest.sha256) { throw 'CPU source hash differs from source.json; sync the generated CPU again' }
    if ($manifest.isa -ne 'rv32ima_zicsr_zifencei' -or $manifest.compressed_instructions -ne $false -or
        $manifest.software_march -ne 'rv32ima_zicsr_zifencei' -or $manifest.abi -ne 'ilp32') {
        throw 'CPU source must use the RV32IMA hardware profile without C'
    }
    if ($manifest.source_path -ne $relativeSource -or $manifest.destination_path -ne $relativeTarget -or
        $manifest.meminit_source_path -ne $relativeMeminit -or
        $manifest.integration_wrapper -ne 'rtl/cpu_top.v' -or $manifest.module -ne 'CoreTop') {
        throw 'CPU source manifest has an unexpected source/interface contract'
    }
    if ($manifest.cpu_version -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or
        $manifest.cpu -cne ('CPU V' + ([regex]::Match($manifest.cpu_version, '^[0-9]+\.[0-9]+')).Value)) {
        throw 'CPU source manifest release version is invalid'
    }
    if (@($manifest.meminit.PSObject.Properties).Count -ne $meminitNames.Count) {
        throw 'CPU source manifest must describe all three memory initialization files'
    }
    foreach ($name in $meminitNames) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $root ('rtl/cpu/meminit/' + $name)) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $manifest.meminit.$name) { throw "CPU memory initialization hash differs: $name" }
    }
    if ($SourceRepo) {
        $version = ([IO.File]::ReadAllText((Join-Path $SourceRepo 'VERSION'))).Trim()
        if ($manifest.cpu_version -cne $version) { throw 'CPU version differs from the selected src checkout' }
        $sourceHash = (Get-FileHash -LiteralPath (Join-Path $SourceRepo $relativeSource) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceHash -ne $actual) { throw 'CPU differs from the selected src checkout' }
        $sourceConfigHash = (Get-FileHash -LiteralPath (Join-Path $SourceRepo $relativeSourceConfig) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceConfigHash -cne $configHash) { throw 'CPU emit configuration differs from the selected src checkout' }
        if ((Get-GeneratorSourceHash $SourceRepo) -ne $manifest.generator_source_sha256) {
            throw 'Generator inputs differ from source.json; regenerate and sync the CPU'
        }
        foreach ($name in $meminitNames) {
            $sourceAsset = Join-Path $SourceRepo ($relativeMeminit + '/' + $name)
            if ((Get-FileHash -LiteralPath $sourceAsset -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.meminit.$name) {
                throw "CPU memory initialization differs from the selected src checkout: $name"
            }
        }
    }
    Write-Output "CPU_SOURCE_CHECK_PASS sha256=$actual"
    return
}
if (!$SourceRepo) { $SourceRepo = Join-Path (Split-Path -Parent $root) 'src' }
$SourceRepo = [IO.Path]::GetFullPath($SourceRepo).TrimEnd('\','/')
Assert-GeneratedSource $SourceRepo
$source = Join-Path $SourceRepo $relativeSource
$sourceConfig = Join-Path $SourceRepo $relativeSourceConfig
Assert-SynthesisConfiguration $sourceConfig ([bool]$AllowSupervisorCandidate)
$configHash = (Get-FileHash -LiteralPath $sourceConfig -Algorithm SHA256).Hash.ToLowerInvariant()
if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Generated CPU missing: $source" }
$sourceText = [IO.File]::ReadAllText($source)
if ($sourceText -notmatch '(?m)^module CoreTop\(' -or $sourceText -notmatch 'io_resetVector') {
    throw 'Source does not expose the supported CoreTop integration interface'
}
if ($sourceText -notmatch $(if ($AllowSupervisorCandidate) { "32'h40141101" } else { "32'h40001101" }) -or
    $sourceText -match "32'h40001105") {
    throw 'Generate the selected CPU RV32IMA profile without C before syncing this CPU'
}
$commit = $null
$dirty = $null
$sourceKind = 'exported_directory'
$git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($git) {
    $gitPreference = $ErrorActionPreference
    try {
        # A ZIP/export need not contain .git. Also do not attribute an exported
        # subtree to an unrelated parent repository found by Git's upward search.
        $ErrorActionPreference = 'Continue'
        $gitRoot = (& $git.Source -C $SourceRepo rev-parse --show-toplevel 2>$null | Out-String).Trim()
        $rootExit = $LASTEXITCODE
        if ($rootExit -eq 0 -and $gitRoot -and
            [IO.Path]::GetFullPath($gitRoot).TrimEnd('\','/') -ieq $SourceRepo) {
            $candidateCommit = (& $git.Source -C $SourceRepo rev-parse HEAD 2>$null | Out-String).Trim()
            $commitExit = $LASTEXITCODE
            if ($commitExit -eq 0 -and $candidateCommit -match '^[0-9a-f]{40,64}$') {
                $status = (& $git.Source -C $SourceRepo status --porcelain -- cpu/src/main cpu/generated/core cpu/scripts/meminit cpu/build.sbt cpu/project/build.properties cpu/project/plugins.sbt | Out-String).Trim()
                if ($LASTEXITCODE) { throw 'Cannot inspect the source Git worktree state' }
                $commit = $candidateCommit
                $dirty = [bool]$status
                $sourceKind = 'git_repository'
            }
        }
    } finally { $ErrorActionPreference = $gitPreference }
}
$generatorHash = Get-GeneratorSourceHash $SourceRepo
New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force
Copy-Item -LiteralPath $sourceConfig -Destination $targetConfig -Force
$meminit = [ordered]@{}
$meminitTarget = Join-Path $root 'rtl/cpu/meminit'
New-Item -ItemType Directory -Path $meminitTarget -Force | Out-Null
foreach ($name in $meminitNames) {
    $sourceAsset = Join-Path $SourceRepo ($relativeMeminit + '/' + $name)
    Copy-Item -LiteralPath $sourceAsset -Destination (Join-Path $meminitTarget $name) -Force
    $meminit[$name] = (Get-FileHash -LiteralPath $sourceAsset -Algorithm SHA256).Hash.ToLowerInvariant()
}
# Reject a concurrent source edit during the copy as well as a stale Emit at
# entry. Local -Check deliberately has no dependency on this source checkout.
Assert-GeneratedSource $SourceRepo
if ((Get-GeneratorSourceHash $SourceRepo) -ne $generatorHash -or
    (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -or
    (Get-FileHash -LiteralPath $sourceConfig -Algorithm SHA256).Hash.ToLowerInvariant() -cne $configHash -or
    (Get-FileHash -LiteralPath $targetConfig -Algorithm SHA256).Hash.ToLowerInvariant() -cne $configHash) {
    throw 'CPU generator, generated RTL or emit configuration changed during synchronization'
}
foreach ($name in $meminitNames) {
    if ((Get-FileHash -LiteralPath (Join-Path $meminitTarget $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $meminit[$name]) {
        throw "CPU initialization changed during synchronization: $name"
    }
}
$cpuVersion = ([IO.File]::ReadAllText((Join-Path $SourceRepo 'VERSION'))).Trim()
if ($cpuVersion -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid source CPU VERSION' }
$cpuDisplay = ([regex]::Match($cpuVersion, '^[0-9]+\.[0-9]+')).Value
$manifest = [ordered]@{
    cpu = "CPU V$cpuDisplay"; cpu_version = $cpuVersion; isa = 'rv32ima_zicsr_zifencei'; abi = 'ilp32'
    software_march = 'rv32ima_zicsr_zifencei'; compressed_instructions = $false
    source_repository = 'src'; source_path = $relativeSource
    source_config_path = $relativeSourceConfig; destination_config_path = $relativeTargetConfig
    config_sha256 = $configHash
    meminit_source_path = $relativeMeminit
    destination_path = $relativeTarget; module = 'CoreTop'
    source_kind = $sourceKind; supervisor_candidate = [bool]$AllowSupervisorCandidate
    source_reference_commit = $commit; source_worktree_dirty = $dirty
    generator_source_sha256 = $generatorHash
    sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    meminit = $meminit
    integration_wrapper = 'rtl/cpu_top.v'
    reset_vector = '0x1c000000'; axi_data_bits = 32; axi_id_bits = 4
    linux_boot = $(if ($AllowSupervisorCandidate) { 'S/U Sv32 candidate; Linux boot not yet tested' } else { 'not tested; current CPU release profile is machine mode' })
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 4) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "CPU_SOURCE_SYNC_PASS sha256=$($manifest.sha256)"
