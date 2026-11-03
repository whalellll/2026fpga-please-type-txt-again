function Get-CompilerCapacityInputs {
    param([string]$Root)
    $names = @('VERSION','config/clocks.json','rtl/cpu/source.json',
        'scripts/build_bootloader.ps1','scripts/riscv_toolchain.ps1',
        'scripts/release_version.ps1','scripts/compiler_capacity_helpers.ps1',
        'scripts/bin_to_hex.ps1')
    foreach ($directory in @('sw/bootloader','sw/coremark')) {
        $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\','/') + '\'
        $names += @(Get-ChildItem -LiteralPath (Join-Path $Root $directory) -File -Recurse |
            ForEach-Object { $_.FullName.Substring($prefix.Length).Replace('\','/') })
    }
    $hashes = [ordered]@{}
    foreach ($name in ($names | Sort-Object)) {
        $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $Root $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $hashes
}

function Get-BootloaderCapacityLayout {
    param([string]$Map, [string]$Elf = '', [string]$Nm = '')
    $text = [IO.File]::ReadAllText($Map)
    $values = @{}
    foreach ($symbol in @('static_memblk','__bss_end','__stack_top')) {
        $found = [regex]::Matches($text, '(?m)^\s*0x([0-9a-fA-F]+)\s+' + [regex]::Escape($symbol) + '(?:\s*=.*)?\s*$')
        # LTO may preserve the local workspace in the ELF but omit it from the map.
        if ($symbol -eq 'static_memblk' -and $found.Count -eq 0 -and $Elf -and $Nm) { continue }
        if ($found.Count -ne 1) { throw "Expected one $symbol in full bootloader map: $Map" }
        $values[$symbol] = [Convert]::ToInt64($found[0].Groups[1].Value,16)
    }
    $symbolSource = 'linker map'
    if ($Elf -or $Nm) {
        if (!$Elf -or !$Nm -or !(Test-Path -LiteralPath $Elf -PathType Leaf) -or
            !(Test-Path -LiteralPath $Nm -PathType Leaf)) { throw 'Both linked ELF and verified toolchain nm are required.' }
        $nmText = (& $Nm -n -S --defined-only $Elf | Out-String)
        if ($LASTEXITCODE) { throw "nm failed for linked bootloader ELF: $Elf" }
        foreach ($symbol in @('static_memblk','__bss_end','__stack_top')) {
            $found = [regex]::Matches($nmText, '(?m)^([0-9a-fA-F]+)\s+(?:([0-9a-fA-F]+)\s+)?([bB])\s+' + [regex]::Escape($symbol) + '\s*$')
            if ($found.Count -ne 1) { throw "Expected one BSS $symbol in linked bootloader ELF: $Elf" }
            $address = [Convert]::ToInt64($found[0].Groups[1].Value,16)
            if ($values.ContainsKey($symbol) -and $values[$symbol] -ne $address) { throw "Map/ELF address mismatch: $symbol" }
            if ($symbol -eq 'static_memblk' -and
                (!$found[0].Groups[2].Success -or [Convert]::ToInt64($found[0].Groups[2].Value,16) -ne 2000)) {
                throw 'Linked CoreMark workspace must be exactly 2000 BSS bytes.'
            }
            $values[$symbol] = $address
        }
        $symbolSource = 'linked ELF symbol table, map boundaries cross-checked'
    }
    $work = $values.static_memblk
    $end = $values.__bss_end
    $top = $values.__stack_top
    if ($work -lt 0x1c000000 -or ($work -band 3) -or $work + 2000 -gt $end -or $top -ne 0x1c01fff0) {
        throw "Unexpected BRAM layout in full bootloader map: $Map"
    }
    return [pscustomobject]@{
        static_memblk = ('0x{0:x8}' -f $work)
        static_memblk_bytes = 2000
        symbol_source = $symbolSource
        bss_end = ('0x{0:x8}' -f $end)
        stack_top = ('0x{0:x8}' -f $top)
        stack_bytes = $top - $end
        stack_minimum_bytes = 16384
        stack_margin_bytes = $top - $end - 16384
        # Preserve the real linker's strict '<', including the equality case.
        stack_gate_passed = $end -lt $top - 16384
    }
}

function Read-CompilerCapacityEvidence {
    param([string]$Path, [string]$Root, $Toolchain, [string]$Optimization)
    $record = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($record.schema_version -ne 1 -or $record.kind -ne 'full_bootloader_compiler_capacity' -or
        $record.result -ne 'PASS' -or $record.coremark_optimization -ne $Optimization -or
        $record.compiler.version -ne $Toolchain.Version -or $record.compiler.target -ne $Toolchain.Target -or
        $record.compiler.sha256 -ne (Get-FileHash -LiteralPath $Toolchain.gcc -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $record.compiler.libgcc_sha256 -ne $Toolchain.LibgccSha256) {
        throw 'Capacity evidence must be a passing complete-image build for this exact compiler, runtime and optimization.'
    }
    $current = Get-CompilerCapacityInputs -Root $Root
    if (@($record.source_files.PSObject.Properties).Count -ne $current.Count) { throw 'Capacity input inventory is stale.' }
    foreach ($name in $current.Keys) {
        if ($record.source_files.$name -ne $current[$name]) { throw "Capacity source/recipe changed: $name" }
    }
    $directory = [IO.Path]::GetFullPath((Split-Path -Parent $Path)).TrimEnd('\','/') + '\'
    foreach ($entry in $record.outputs.PSObject.Properties) {
        $full = [IO.Path]::GetFullPath((Join-Path $directory $entry.Name))
        if (!$full.StartsWith($directory,[StringComparison]::OrdinalIgnoreCase) -or
            (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
            throw "Capacity output changed or escaped evidence directory: $($entry.Name)"
        }
    }
    foreach ($name in @('bootloader.map','bootloader.build.json','bootloader.elf','bootloader.bin','bootrom.hex')) {
        if (!$record.outputs.("project/artifacts/$name")) { throw "Capacity evidence lacks complete build output: $name" }
    }
    $layout = Get-BootloaderCapacityLayout -Map (Join-Path $directory 'project/artifacts/bootloader.map') `
        -Elf (Join-Path $directory 'project/artifacts/bootloader.elf') -Nm $Toolchain.nm
    if (!$layout.stack_gate_passed -or $layout.static_memblk -ne $record.layout.static_memblk -or
        $layout.bss_end -ne $record.layout.bss_end -or $layout.stack_bytes -ne $record.layout.stack_bytes) {
        throw 'Capacity map does not match its layout or fails the original stack gate.'
    }
    return [pscustomobject]@{
        evidence_sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        map_sha256 = $record.outputs.'project/artifacts/bootloader.map'
        static_memblk = $layout.static_memblk
        stack_bytes = $layout.stack_bytes
    }
}
