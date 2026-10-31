[CmdletBinding()]
param(
    [switch]$GeneratedCpu,
    [string]$FirmwareDirectory = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\', '/')
if (!$GeneratedCpu -and !$FirmwareDirectory) { throw 'Select -GeneratedCpu and/or -FirmwareDirectory.' }

function Get-ContainedFile([string]$Root, [string]$Relative) {
    # JSON paths are portable, canonical names, never shell paths or aliases.
    if (!$Relative -or [IO.Path]::IsPathRooted($Relative) -or
        $Relative -match '[\\<>:"|?*]' -or
        @($Relative.Split('/') | Where-Object { !$_ -or $_ -eq '.' -or $_ -eq '..' -or $_ -match '[ .]$' }).Count) {
        throw "Manifest contains a noncanonical relative path: $Relative"
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (!$path.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes its root: $Relative"
    }
    $current = $path
    while ($true) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Manifest input follows a linked file/directory: $Relative"
        }
        if ($current -eq $base) { break }
        $current = Split-Path -Parent $current
    }
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Manifest input is not a regular file: $Relative" }
    return $path
}

function Get-InputMap([object]$Map, [string]$Label) {
    if ($null -eq $Map -or $Map -isnot [pscustomobject]) { throw "Missing or invalid $Label map." }
    $result = New-Object 'Collections.Generic.Dictionary[string,string]' ([StringComparer]::Ordinal)
    foreach ($entry in $Map.PSObject.Properties) {
        if ($entry.Value -isnot [string] -or $entry.Value -notmatch '^[0-9a-fA-F]{64}$') {
            throw "Invalid SHA256 in ${Label}: $($entry.Name)"
        }
        $result.Add($entry.Name, $entry.Value.ToLowerInvariant())
    }
    if (!$result.Count) { throw "Empty $Label map." }
    return ,$result
}

function Assert-Map([object]$Map, [string[]]$Expected, [string]$Root, [string]$Label) {
    $entries = Get-InputMap $Map $Label
    $expectedSet = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($name in $Expected) { [void]$expectedSet.Add($name) }
    if ($entries.Count -ne $expectedSet.Count -or
        @($entries.Keys | Where-Object { !$expectedSet.Contains($_) }).Count) {
        throw "$Label file set differs from the current inputs; rebuild before preparing this checkout."
    }
    foreach ($entry in $entries.GetEnumerator()) {
        $path = Get-ContainedFile $Root $entry.Key
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $entry.Value) { throw "$Label changed: $($entry.Key); rebuild before preparing this checkout." }
    }
}

function Get-TreeFiles([string]$Directory) {
    # Do not traverse links, including directory junctions on Windows PowerShell 5.
    $pending = New-Object 'Collections.Generic.Stack[string]'
    $pending.Push($Directory)
    while ($pending.Count) {
        $directoryPath = $pending.Pop()
        $directoryItem = Get-Item -LiteralPath $directoryPath -Force
        if (!$directoryItem.PSIsContainer -or ($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Input directory is missing or linked: $directoryPath"
        }
        foreach ($item in Get-ChildItem -LiteralPath $directoryPath -Force) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked input: $($item.FullName)" }
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else { $item.FullName.Substring($projectRoot.Length + 1).Replace('\', '/') }
        }
    }
}

function Assert-EmitKeys($Object, [string[]]$Expected, [string]$Label) {
    if ($Object -isnot [pscustomobject]) { throw "Invalid $Label object." }
    $names = @($Object.PSObject.Properties.Name)
    if ($names.Count -ne $Expected.Count -or @($names | Where-Object { $_ -cnotin $Expected }).Count) {
        throw "$Label has missing or unsupported fields."
    }
}

function Assert-EmitArchitecture($Architecture) {
    $names = @('aluEntries', 'memEntries', 'fallbackSets', 'fallbackHash', 'rasDepth')
    Assert-EmitKeys $Architecture $names 'Architecture configuration'
    foreach ($name in $names) {
        $value = $Architecture.$name
        if ($name -eq 'fallbackHash') {
            if ($value -isnot [bool]) { throw 'fallbackHash must be a JSON boolean.' }
        } elseif (($value -isnot [int] -and $value -isnot [long]) -or $value -lt 1 -or $value -gt 2147483647) {
            throw "$name must be a positive JSON integer."
        }
    }
}

function Read-EmitConfiguration([string]$Path, [bool]$Synthesis) {
    $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-EmitKeys $value @('schema_version', 'isa', 'supervisor', 'architecture', 'cache', 'mode') 'Emit configuration'
    if (($value.schema_version -isnot [int] -and $value.schema_version -isnot [long]) -or
        $value.schema_version -ne 1 -or $value.isa -cne 'rv32ima_zicsr_zifencei' -or
        $value.supervisor -isnot [bool]) { throw 'Unsupported emit ISA/profile/schema.' }
    Assert-EmitArchitecture $value.architecture
    Assert-EmitKeys $value.cache @('lineBytes', 'l1Sets', 'iWays', 'dWays', 'l2Sets', 'l2Ways') 'Cache configuration'
    foreach ($entry in $value.cache.PSObject.Properties) {
        if (($entry.Value -isnot [int] -and $entry.Value -isnot [long]) -or
            $entry.Value -lt 1 -or $entry.Value -gt 2147483647) { throw "Invalid cache configuration: $($entry.Name)" }
    }
    Assert-EmitKeys $value.mode @('synthesis', 'socProbes') 'Emit mode'
    if ($value.mode.synthesis -isnot [bool] -or $value.mode.socProbes -isnot [bool] -or
        $value.mode.synthesis -ne $Synthesis -or $value.mode.socProbes -ne (!$Synthesis)) {
        throw "Wrong synthesis/simulation probe mode in $Path"
    }
    return $value
}

if ($GeneratedCpu) {
    $manifestPath = Get-ContainedFile $projectRoot 'generated/manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-EmitKeys $manifest @('schema_version', 'purpose', 'generation', 'architecture', 'source_files', 'outputs') 'Generated CPU manifest'
    if (($manifest.schema_version -isnot [int] -and $manifest.schema_version -isnot [long]) -or
        $manifest.schema_version -ne 2 -or $manifest.purpose -cne 'CPU source to generated RTL binding') {
        throw 'Expected generated CPU manifest schema 2; schema 1 is historical. Run newpc.ps1 -Stage Emit.'
    }
    $inputs = @('build.sbt') + @(Get-TreeFiles (Join-Path $projectRoot 'src/main'))
    foreach ($directory in @('project', 'scripts/meminit')) {
        $entries = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot $directory) -Force)
        foreach ($item in $entries) {
            $isInput = if ($directory -eq 'project') { $item.Extension -in @('.sbt', '.properties') } else { $item.Extension -eq '.hex' }
            if ($isInput -and !$item.PSIsContainer) { $inputs += "$directory/$($item.Name)" }
        }
    }
    Assert-Map $manifest.source_files $inputs $projectRoot 'Generated CPU source/config/init'
    Assert-Map $manifest.outputs @('generated/core/CoreTop.sv', 'generated/sim/CoreTop.sv',
        'generated/core/emit-config.json', 'generated/sim/emit-config.json') $projectRoot 'Generated CPU output'
    $core = Read-EmitConfiguration (Get-ContainedFile $projectRoot 'generated/core/emit-config.json') $true
    $sim = Read-EmitConfiguration (Get-ContainedFile $projectRoot 'generated/sim/emit-config.json') $false
    Assert-EmitArchitecture $manifest.architecture
    foreach ($name in @('aluEntries', 'memEntries', 'fallbackSets', 'fallbackHash', 'rasDepth')) {
        if ($core.architecture.$name -cne $sim.architecture.$name -or
            $core.architecture.$name -cne $manifest.architecture.$name) {
            throw "Synthesis/simulation/manifest architecture differs: $name"
        }
    }
    foreach ($name in @('lineBytes', 'l1Sets', 'iWays', 'dWays', 'l2Sets', 'l2Ways')) {
        if ($core.cache.$name -cne $sim.cache.$name) { throw "Synthesis and simulation cache configurations differ: $name" }
    }
    $flags = (@('aluEntries', 'memEntries', 'fallbackSets', 'fallbackHash', 'rasDepth') | ForEach-Object {
        $setting = [string]$core.architecture.$_
        '-De91c.' + $_ + '=' + $setting.ToLowerInvariant()
    }) -join ' '
    if ($core.supervisor -cne $sim.supervisor) { throw 'Synthesis/simulation supervisor profiles differ.' }
    $profile = if ($core.supervisor) { ' -De91c.supervisor=true' } else { '' }
    $generation = @(
        ($flags + $profile + ' -De91c.socProbes=false runMain e91c.core.EmitCore generated/core --synthesis'),
        ($flags + $profile + ' -De91c.socProbes=true runMain e91c.core.EmitCore work/handoff-probes'))
    if ($manifest.generation -isnot [array] -or $manifest.generation.Count -ne 2 -or
        $manifest.generation[0] -cne $generation[0] -or $manifest.generation[1] -cne $generation[1]) {
        throw 'Recorded reproduction arguments differ from the actual emitted architecture.'
    }
    Write-Output 'GENERATED_RTL_INPUTS_PASS'
}

if ($FirmwareDirectory) {
    $FirmwareDirectory = [IO.Path]::GetFullPath($FirmwareDirectory).TrimEnd('\', '/')
    $manifestPath = Get-ContainedFile $FirmwareDirectory 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (($manifest.schema_version -isnot [int] -and $manifest.schema_version -isnot [long]) -or
        $manifest.schema_version -ne 3) { throw 'Unsupported firmware manifest; rebuild with scripts/build_coremark.ps1.' }
    if ($manifest.run_mode -cnotin @('performance', 'validation') -or $manifest.tick_report -cne 'PORT_TICKS64' -or
        $manifest.coremark_upstream -cne 'cfa9ab377835911f23d9b0831c7be302ed1f58de' -or
        $manifest.coremark_sim -isnot [bool] -or $manifest.coremark_sim -ne $false) {
        throw 'Firmware must use official CoreMark seeds, unmodified time checks and PORT_TICKS64.'
    }
    if ($manifest.isa -cne 'rv32ima' -or $manifest.march -cne 'rv32ima_zicsr_zifencei' -or
        $manifest.abi -cne 'ilp32' -or $manifest.compressed_instructions -ne 0 -or
        ($manifest.compressed_instructions -isnot [int] -and $manifest.compressed_instructions -isnot [long]) -or
        $manifest.compiler_target -cne 'riscv32-unknown-elf' -or $manifest.optimization -cnotin @('-O2', '-O3')) {
        throw 'Unexpected firmware ISA, ABI, compiler target or optimization.'
    }
    foreach ($name in @('cpu_hz', 'iterations')) {
        $maximum = if ($name -eq 'cpu_hz') { 1000000000 } else { 2147483647 }
        if (($manifest.$name -isnot [int] -and $manifest.$name -isnot [long]) -or
            $manifest.$name -lt 1 -or $manifest.$name -gt $maximum) { throw "Invalid firmware $name" }
    }
    $inputs = @('coremark_test_soc/sw/start.S', 'coremark_test_soc/sw/link.ld',
        'scripts/build_coremark.ps1', 'coremark_test_soc/sw/coremark/upstream.json')
    $inputs += @(Get-TreeFiles (Join-Path $projectRoot 'coremark_test_soc/sw/coremark') | Where-Object { $_ -match '\.[ch]$' })
    Assert-Map $manifest.source_files $inputs $projectRoot 'Firmware source/recipe/upstream'
    Assert-Map $manifest.files @('coremark.elf', 'coremark.bin', 'ram.hex', 'macros.txt', 'coremark_build_config.h') $FirmwareDirectory 'Firmware output'
    $definitions = [ordered]@{
        ITERATIONS = "$($manifest.iterations)"
        PERFORMANCE_RUN = "$([int]($manifest.run_mode -eq 'performance'))"
        VALIDATION_RUN = "$([int]($manifest.run_mode -eq 'validation'))"
        PROFILE_RUN = '0'; CORE_CLOCKS_PER_SEC = "$($manifest.cpu_hz)ULL"
        COMPILER_VERSION = '"GCC ' + $manifest.compiler_version + ' (riscv32-unknown-elf)"'
        COMPILER_FLAGS = '"' + $manifest.compiler_flags + '"'
    }
    foreach ($filename in @('coremark_build_config.h', 'macros.txt')) {
        $text = [IO.File]::ReadAllText((Get-ContainedFile $FirmwareDirectory $filename))
        foreach ($name in $definitions.Keys) {
            $values = [regex]::Matches($text, ('(?m)^#define\s+' + $name + '\s+([^\r\n]+)'))
            if ($values.Count -ne 1 -or $values[0].Groups[1].Value -cne $definitions[$name]) {
                throw "Firmware manifest disagrees with ${filename}: $name"
            }
        }
    }
    Write-Output 'FIRMWARE_INPUTS_PASS'
}
