param(
    [Parameter(Mandatory = $true)][string]$Vm,
    [Parameter(Mandatory = $true)][string]$Snapshot,
    [Parameter(Mandatory = $true)][string]$CdcAuditJson,
    [Parameter(Mandatory = $true)][string]$ExpectedRunId,
    [Parameter(Mandatory = $true)][string]$ResultDirectory,
    [switch]$PreflightOnly,
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$VendorModels = 'D:\LJL\WORK\pango\PDS_2022.2-SP6.4\arch\vendor\pango\verilog\simulation'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$stage = $PSScriptRoot
$root = (Resolve-Path -LiteralPath (Join-Path $stage '..')).Path
$vmPath = (Resolve-Path -LiteralPath $Vm).Path
$snapshotPath = (Resolve-Path -LiteralPath $Snapshot).Path
$auditPath = (Resolve-Path -LiteralPath $CdcAuditJson).Path
if ($ExpectedRunId -cnotmatch '^[0-9a-f]{32}$') { throw 'ExpectedRunId must be a 32-digit lowercase run ID.' }
$audit = Get-Content -LiteralPath $auditPath -Raw | ConvertFrom-Json
$snapshotData = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json
$vmHash = (Get-FileHash -LiteralPath $vmPath -Algorithm SHA256).Hash.ToLowerInvariant()
$snapshotHash = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
$auditHash = (Get-FileHash -LiteralPath $auditPath -Algorithm SHA256).Hash.ToLowerInvariant()
$runnerHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($snapshotData.run_id -cne $ExpectedRunId -or
    $audit.schema -ne 1 -or
    $audit.status -cne 'PASS' -or $audit.run_id -cne $ExpectedRunId -or
    $audit.vm_sha256 -cne $vmHash -or
    $audit.snapshot_sha256 -cne $snapshotHash -or
    $audit.fdc_sha256 -cne $snapshotData.inputs.'pds/soc.fdc') {
    throw 'VM, CDC ADS audit, and frozen input snapshot do not belong to the same passing run.'
}
if ($audit.constraints.total_constraints -ne 1171 -or
    $audit.constraints.cdc_directives -ne 48 -or
    $audit.constraints.gray_directives -ne 30 -or
    $audit.constraints.payload_directives -ne 10 -or
    $audit.constraints.first_stage_directives -ne 8 -or
    $audit.constraints.mapped_endpoint_tags -ne 300 -or
    $audit.constraints.mapped_payload_output_tags -ne 298 -or
    $audit.constraints.mapped_first_stage_tags -ne 8 -or
    $audit.constraints.mapped_second_stage_tags -ne 4 -or
    $audit.constraints.errors -ne 0 -or
    $audit.constraints.critical_warnings -ne 39 -or
    $audit.constraints.warnings -ne 0 -or
    @($audit.fifos).Count -ne 10 -or
    @($audit.payloads).Count -ne 5 -or
    @($audit.first_stage_crossings).Count -ne 4) {
    throw 'CDC ADS audit lacks the reviewed mapped endpoint or constraint coverage.'
}
foreach ($name in @('rtl/clint.v', 'rtl/soc/axi_cpu_sys_cdc.v')) {
    $expectedSourceHash = $snapshotData.inputs.PSObject.Properties[$name].Value
    $actualSourceHash = (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expectedSourceHash -cne $actualSourceHash) {
        throw "Frozen $name differs from the current release source."
    }
}

$source = [IO.File]::ReadAllText($vmPath)
function Get-MappedModule {
    param([string]$Name)
    $matches = [regex]::Matches($source, '(?ms)^module\s+' + [regex]::Escape($Name) + '\s*\(.*?^endmodule')
    if ($matches.Count -ne 1) { throw "Expected one mapped module $Name; found $($matches.Count)." }
    return $matches[0].Value
}
function Get-Ports {
    param([string]$Body)
    $headerEnd = $Body.IndexOf(');')
    if ($headerEnd -lt 0) { throw 'Mapped module has no header terminator.' }
    $header = $Body.Substring(0, $headerEnd)
    $found = [regex]::Matches($header,
        '(?m)^\s*(?:input|output)\s+(?:\[[0-9:]+\]\s*)?(\\?[^\s,]+)\s*(?:,|$)')
    return @($found | ForEach-Object { $_.Groups[1].Value.TrimStart([char]'\') })
}
function Get-InputPorts {
    param([string]$Body)
    $headerEnd = $Body.IndexOf(');')
    if ($headerEnd -lt 0) { throw 'Mapped module has no header terminator.' }
    $header = $Body.Substring(0, $headerEnd)
    $found = [regex]::Matches($header,
        '(?m)^\s*input\s+(?:\[[0-9:]+\]\s*)?(\\?[^\s,]+)\s*(?:,|$)')
    return @($found | ForEach-Object { $_.Groups[1].Value.TrimStart([char]'\') })
}
function Assert-Ports {
    param([string]$Name, [string]$Body, [string[]]$Expected)
    $actual = @(Get-Ports -Body $Body)
    $bad = $actual.Count -ne $Expected.Count
    for ($index = 0; !$bad -and $index -lt $Expected.Count; $index++) {
        if ($Expected[$index] -ceq '<mapped_N>') {
            $bad = $actual[$index] -cnotmatch '^_N[0-9]+$'
        } else {
            $bad = $actual[$index] -cne $Expected[$index]
        }
    }
    if ($bad) {
        throw "Mapped $Name positional interface changed; adapt the gate testbench before running. Actual: $($actual -join ', ')"
    }
}
function Get-RamBits {
    param([string]$Body, [string]$Direction)
    $port = if ($Direction -eq 'read') { 'DO' } else { 'DI' }
    $prefix = if ($Direction -eq 'read') { 'rd_data' } else { 'wr_data' }
    $bits = @()
    foreach ($connection in [regex]::Matches($Body, '\.' + $port + '\s*\(([^)]*)\)')) {
        foreach ($bit in [regex]::Matches($connection.Groups[1].Value,
                [regex]::Escape($prefix) + '\[(\d+)\]')) {
            $bits += [int]$bit.Groups[1].Value
        }
    }
    return @($bits | Sort-Object -Unique)
}

$bridge = Get-MappedModule -Name 'axi_cpu_sys_cdc'
$bType = [regex]::Matches($bridge, '(?m)^\s*(axi_async_fifo\w*)\s+u_b_fifo\s*\(')
$rType = [regex]::Matches($bridge, '(?m)^\s*(axi_async_fifo\w*)\s+u_r_fifo\s*\(')
if ($bType.Count -ne 1 -or $rType.Count -ne 1 -or
    $bType[0].Groups[1].Value -cne 'axi_async_fifo_3' -or
    $rType[0].Groups[1].Value -cne 'axi_async_fifo_2') {
    throw 'Mapped B/R FIFO module identity changed; adapt the gate testbenches.'
}
$bBody = Get-MappedModule -Name 'axi_async_fifo_3'
$rBody = Get-MappedModule -Name 'axi_async_fifo_2'
$clintBody = Get-MappedModule -Name 'clint'
Assert-Ports -Name 'B FIFO' -Body $bBody -Expected @(
    'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_axi_line_bridge/bCnt',
    'wr_data','rd_clk','u_cpu/u_cpu_wrapper/c_bvalid',
    'u_cpu/u_cpu_wrapper/u_axi_cdc/N0_1',
    'u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3',
    'wr_clk','wr_fire','rd_data','rd_gray','rd_gray_wr2',
    'wr_gray','wr_gray_rd2','<mapped_N>','<mapped_N>','rd_fire')
Assert-Ports -Name 'R FIFO' -Body $rBody -Expected @(
    'wr_data','rd_clk','rd_fire','u_cpu/u_cpu_wrapper/u_axi_cdc/N0_1',
    'u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3',
    'wr_clk','wr_fire','rd_data','rd_gray','rd_gray_wr2','wr_gray',
    'wr_gray_rd2','<mapped_N>','<mapped_N>')
$expectedB = @(1)
$expectedR = @(0) + @(2..36)
foreach ($direction in @('read','write')) {
    $actualB = @(Get-RamBits -Body $bBody -Direction $direction)
    $actualR = @(Get-RamBits -Body $rBody -Direction $direction)
    if (($actualB -join ',') -cne ($expectedB -join ',') -or
        ($actualR -join ',') -cne ($expectedR -join ',')) {
        throw "Mapped FIFO $direction payload-bit retention changed; adapt the scoreboard mask."
    }
}
$clintInputs = @(Get-InputPorts -Body $clintBody)
$expectedClintInputs = @(
    'addr','d_araddr','l_araddr','l_wdata','l_wstrb',
    'u_cpu/u_cpu_wrapper/local_wr_addr','clk','cyc',
    'u_cpu/u_cpu_wrapper/local_write_fire',
    'u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3')
$sharedIoClintInputs = @(
    'addr','d_araddr','io_addr','l_araddr','l_wdata','l_wstrb',
    'u_cpu/u_cpu_wrapper/local_wr_addr','_N321426','clk','cyc',
    'io_wr','sd_hit','u_cpu/u_cpu_wrapper/local_write_fire',
    'u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3','u_sd/busy')
$sharedIoClint = ($clintInputs -join '|') -ceq ($sharedIoClintInputs -join '|')
if (!$sharedIoClint -and
    ($clintInputs -join '|') -cne ($expectedClintInputs -join '|')) {
    throw "Mapped CLINT input interface changed; adapt the gate testbench. Actual: $($clintInputs -join ', ')"
}
if ($sharedIoClint) {
    # ADS placed an unrelated SD I/O decode LUT in the CLINT module. Verify
    # its extra inputs drive only that output before tying them in isolation.
    $sharedIoCounts = @{
        'io_addr' = 3; '_N321426' = 2; 'io_wr' = 2
        'sd_hit' = 2; 'u_sd/busy' = 2; '_N322820' = 2
    }
    foreach ($name in $sharedIoCounts.Keys) {
        if ([regex]::Matches($clintBody, [regex]::Escape($name)).Count -ne
            $sharedIoCounts[$name]) {
            throw "Mapped CLINT shared I/O signal $name has unexpected internal uses."
        }
    }
    if ($clintBody -cnotmatch '(?s)\.Z \(_N322820\),\s*\.I0 \(io_wr\),\s*\.I1 \(sd_hit\),\s*\.I2 \(io_addr\[2\]\),\s*\.I3 \(io_addr\[4\]\),\s*\.I4 \(_N321426\),\s*\.I5 \(\\u_sd/busy\s+\)') {
        throw 'Mapped CLINT shared I/O decode LUT changed.'
    }
}
$clintPorts = @(Get-Ports -Body $clintBody)
foreach ($name in @('rdata','ack','software_irq','timer_irq')) {
    if ($clintPorts -cnotcontains $name) { throw "Mapped CLINT output $name is missing." }
}
$mtimeFfs = [regex]::Matches($clintBody,
    'GTP_DFF_RE\s*/\*\s*\\mtime\[([0-9]+)\]\s*\*/')
if ($mtimeFfs.Count -ne 64 -or
    (@($mtimeFfs | ForEach-Object { [int]$_.Groups[1].Value } | Sort-Object -Unique) -join ',') -cne ((0..63) -join ',')) {
    throw 'Mapped CLINT does not retain exactly 64 mtime flip-flops.'
}
foreach ($path in @((Join-Path $stage 'tb_mapped_b_fifo.sv'),
        (Join-Path $stage 'tb_mapped_r_fifo.sv'),
        (Join-Path $stage 'tb_mapped_clint_zero_wstrb.sv'),
        (Join-Path $IcarusBin 'iverilog.exe'),
        (Join-Path $IcarusBin 'vvp.exe'),
        (Join-Path $VendorModels 'GTP_GRS.v'))) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing mapped gate input: $path" }
}
function Get-VendorModelInventory {
    param([string]$Directory)
    if (!(Test-Path -LiteralPath $Directory -PathType Container)) {
        throw "Missing Pango vendor model directory: $Directory"
    }
    [string[]]$models = @([IO.Directory]::GetFiles($Directory, '*',
        [IO.SearchOption]::TopDirectoryOnly) | Where-Object {
            [IO.Path]::GetExtension($_) -ceq '.v'
        })
    [Array]::Sort($models, [StringComparer]::Ordinal)
    if ($models.Count -ne 319) {
        throw "Pango vendor model inventory changed: expected 319 .v files, found $($models.Count)."
    }
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($model in $models) {
        if (([IO.File]::GetAttributes($model) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Vendor model must be a regular file: $model"
        }
        $hash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()
        $lines.Add($hash + '  ' + [IO.Path]::GetFileName($model))
    }
    return ($lines -join "`n") + "`n"
}
$vendorInventory = Get-VendorModelInventory -Directory $VendorModels
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
$iverilogHash = (Get-FileHash -LiteralPath $iverilog -Algorithm SHA256).Hash.ToLowerInvariant()
$vvpHash = (Get-FileHash -LiteralPath $vvp -Algorithm SHA256).Hash.ToLowerInvariant()
$testbenchHashes = [ordered]@{}
foreach ($name in @('tb_mapped_b_fifo.sv','tb_mapped_r_fifo.sv',
        'tb_mapped_clint_zero_wstrb.sv')) {
    $testbenchHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
Write-Output "MAPPED_GATE_PREFLIGHT_PASS run=$ExpectedRunId vm=$vmHash B_bits=1 R_bits=36 CLINT_mtime_ff=64"
if ($PreflightOnly) { return }

$resultPath = [IO.Path]::GetFullPath($ResultDirectory)
if (Test-Path -LiteralPath $resultPath) { throw 'ResultDirectory already exists; use a new path for this run.' }
$null = New-Item -ItemType Directory -Path $resultPath
$vendorInventoryPath = Join-Path $resultPath 'vendor_models.sha256'
[IO.File]::WriteAllText($vendorInventoryPath, $vendorInventory,
    [Text.UTF8Encoding]::new($false))
if (!('CpuSimulation.BoundedProcess' -as [type])) {
    Add-Type -Path (Join-Path $root 'scripts/bounded_process.cs')
}
$deadline = [DateTime]::UtcNow.AddMinutes(5)
Write-Output "MAPPED_CDC_OWNER_PID=$PID deadline_utc=$($deadline.ToString('o'))"
Write-Output 'End this owner PowerShell process to stop its Windows Job children.'
function Invoke-Bounded {
    param([string]$Executable, [string]$Arguments, [string]$Name, [int]$LimitSeconds)
    $remaining = [int][Math]::Floor(($deadline - [DateTime]::UtcNow).TotalSeconds)
    if ($remaining -le 0) { throw 'Mapped CDC gate deadline expired.' }
    $timeout = [Math]::Min($LimitSeconds, $remaining)
    $stdout = Join-Path $resultPath ($Name + '.stdout.log')
    $stderr = Join-Path $resultPath ($Name + '.stderr.log')
    $code = [CpuSimulation.BoundedProcess]::Run($Executable, $Arguments,
        $root, $stdout, $stderr, $timeout)
    if ($code -ne 0) { throw "$Name exited $code; see $stdout and $stderr" }
    return $stdout
}

$cases = @(
    @{ cpu = 7; sys = 11; phase = 3; seed = 439041101 },
    @{ cpu = 13; sys = 5; phase = 2; seed = 1515870810 },
    @{ cpu = 10; sys = 10; phase = 4; seed = 305419896 }
)
$commandLines = [System.Collections.Generic.List[string]]::new()
$caseResults = @()
foreach ($channel in @('b','r')) {
    $top = 'tb_mapped_' + $channel + '_fifo'
    $tb = Join-Path $stage ($top + '.sv')
    $image = Join-Path $resultPath ($top + '.vvp')
    $compileArgs = '-g2012 -s ' + $top + ' -o "' + $image +
        '" -y "' + $VendorModels + '" "' + $tb + '" "' + $vmPath + '"'
    $commandLines.Add('"' + $iverilog + '" ' + $compileArgs)
    $null = Invoke-Bounded -Executable $iverilog -Arguments $compileArgs `
        -Name ('compile_' + $channel) -LimitSeconds 60
    foreach ($case in $cases) {
        $name = $channel + '_' + $case.cpu + '_' + $case.sys + '_' + $case.phase
        $argsText = '"' + $image + '" +cpu_half=' + $case.cpu +
            ' +sys_half=' + $case.sys + ' +sys_phase=' + $case.phase +
            ' +seed=' + $case.seed
        $commandLines.Add('"' + $vvp + '" ' + $argsText)
        $logPath = Invoke-Bounded -Executable $vvp -Arguments $argsText `
            -Name $name -LimitSeconds 30
        $log = [IO.File]::ReadAllText($logPath)
        $marker = 'MAPPED_' + $channel.ToUpperInvariant() +
            '_FIFO_PASS cpu_half=' + $case.cpu + ' sys_half=' + $case.sys +
            ' phase=' + $case.phase + ' seed=' + $case.seed
        $passLine = '(?m)^' + [regex]::Escape($marker) +
            ' writes=\d+ reads=\d+ reset_pending=\d+ wr_stalls=\d+ rd_stalls=\d+\r?$'
        if ([regex]::Matches($log, $passLine).Count -ne 1 -or
            $log.Contains('FATAL:')) { throw "Scoreboard marker missing or fatal in $logPath" }
        $caseResults += [ordered]@{
            channel = $channel; cpu_half = $case.cpu; sys_half = $case.sys
            phase = $case.phase; seed = $case.seed; marker = $marker
            stdout_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$clintTop = 'tb_mapped_clint_zero_wstrb'
$clintTb = Join-Path $stage ($clintTop + '.sv')
$clintImage = Join-Path $resultPath ($clintTop + '.vvp')
$clintDefines = if ($sharedIoClint) { ' -DCLINT_SHARED_IO_VM' } else { '' }
$clintCompileArgs = '-g2012' + $clintDefines + ' -s ' + $clintTop + ' -o "' + $clintImage +
    '" -y "' + $VendorModels + '" "' + $clintTb + '" "' + $vmPath + '"'
$commandLines.Add('"' + $iverilog + '" ' + $clintCompileArgs)
$null = Invoke-Bounded -Executable $iverilog -Arguments $clintCompileArgs `
    -Name 'compile_clint' -LimitSeconds 60
$clintRunArgs = '"' + $clintImage + '"'
$commandLines.Add('"' + $vvp + '" ' + $clintRunArgs)
$clintLogPath = Invoke-Bounded -Executable $vvp -Arguments $clintRunArgs `
    -Name 'clint' -LimitSeconds 30
$clintLog = [IO.File]::ReadAllText($clintLogPath)
if ($clintLog -cnotmatch '(?m)^MAPPED_CLINT_ZERO_WSTRB_PASS ordinary=2 zero=2 final_mtime=[0-9a-fA-F]{16}\r?$' -or
    $clintLog.Contains('FATAL:')) {
    throw "Mapped CLINT scoreboard marker missing or fatal in $clintLogPath"
}

if ((Get-FileHash -LiteralPath $vmPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $vmHash -or
    (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $snapshotHash -or
    (Get-FileHash -LiteralPath $auditPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $auditHash -or
    (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $runnerHash -or
    (Get-FileHash -LiteralPath $iverilog -Algorithm SHA256).Hash.ToLowerInvariant() -cne $iverilogHash -or
    (Get-FileHash -LiteralPath $vvp -Algorithm SHA256).Hash.ToLowerInvariant() -cne $vvpHash -or
    (Get-VendorModelInventory -Directory $VendorModels) -cne $vendorInventory -or
    [IO.File]::ReadAllText($vendorInventoryPath) -cne $vendorInventory) {
    throw 'VM, audit, runner, Icarus binaries, or vendor models changed during simulation.'
}
foreach ($name in $testbenchHashes.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne
        $testbenchHashes[$name]) {
        throw "Mapped gate testbench $name changed during simulation."
    }
}
$commandFile = Join-Path $resultPath 'commands.txt'
[IO.File]::WriteAllText($commandFile, ($commandLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false))
$result = [ordered]@{
    schema_version = 1; status = 'PASS'; run_id = $ExpectedRunId
    scope = 'exact SoC ADS VM B/R FIFO submodules and CLINT mtime; zero delay; no SDF'
    vm_sha256 = $vmHash; snapshot_sha256 = $snapshotHash
    cdc_audit_sha256 = $auditHash; runner_sha256 = $runnerHash
    b_tb_sha256 = $testbenchHashes['tb_mapped_b_fifo.sv']
    r_tb_sha256 = $testbenchHashes['tb_mapped_r_fifo.sv']
    clint_tb_sha256 = $testbenchHashes['tb_mapped_clint_zero_wstrb.sv']
    iverilog_sha256 = $iverilogHash
    vvp_sha256 = $vvpHash
    vendor_models_count = 319
    vendor_models_inventory_sha256 = (Get-FileHash -LiteralPath $vendorInventoryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    gtp_grs_model_sha256 = (Get-FileHash -LiteralPath (Join-Path $VendorModels 'GTP_GRS.v') -Algorithm SHA256).Hash.ToLowerInvariant()
    clint_stdout_sha256 = (Get-FileHash -LiteralPath $clintLogPath -Algorithm SHA256).Hash.ToLowerInvariant()
    command_file_sha256 = (Get-FileHash -LiteralPath $commandFile -Algorithm SHA256).Hash.ToLowerInvariant()
    cases = $caseResults; completed_utc = [DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $resultPath 'result.json'),
    ($result | ConvertTo-Json -Depth 6) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "MAPPED_CDC_CLINT_GATE_PASS run=$ExpectedRunId vm=$vmHash fifo_cases=$($caseResults.Count) clint_cases=4"
