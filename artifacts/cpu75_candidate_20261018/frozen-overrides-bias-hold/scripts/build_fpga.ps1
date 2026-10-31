param(
    [string]$PdsShell = '',
    [string]$ToolchainRoot = '',
    [string]$Distro = 'chiplab_sim',
    [string]$PythonPath = '',
    [ValidateRange(1, 86400)][int]$PdsTimeoutSeconds = 7200,
    [switch]$RebuildHdmiAssets,
    [switch]$UseExistingFirmware,
    [switch]$SynthesisOnly,
    [switch]$FinalizeCompletedBuild,
    [switch]$CheckSdStorageOnly,
    [datetime]$BuildStartedUtc = [datetime]::MinValue,
    [string]$CampaignBudget = '',
    [ValidateSet('search','same_frequency','final')][string]$AttemptPurpose = 'search'
)

$ErrorActionPreference = 'Stop'
if ($SynthesisOnly -and ($FinalizeCompletedBuild -or $CheckSdStorageOnly -or $RebuildHdmiAssets)) {
    throw 'SynthesisOnly cannot be combined with finalization, SD-only checking, or HDMI regeneration'
}
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'build_pnr_budget.ps1')
if (!$FinalizeCompletedBuild -and !$CheckSdStorageOnly -and !$SynthesisOnly) {
    $CampaignBudget = Resolve-PnrCampaignBudget $root $CampaignBudget
    if ($CampaignBudget) { [void](Get-PnrCampaignSeconds $CampaignBudget $AttemptPurpose) }
}
if ($RebuildHdmiAssets -and ($FinalizeCompletedBuild -or $CheckSdStorageOnly)) {
    throw '-RebuildHdmiAssets applies only to a new complete build'
}
if ($UseExistingFirmware -and $RebuildHdmiAssets) {
    throw '-UseExistingFirmware cannot be combined with HDMI asset regeneration'
}

function Invoke-FpgaPdsJob {
    param([string]$Executable, [string]$Directory, [string]$LogPrefix,
        [int]$TimeoutSeconds, [Parameter(Mandatory=$true)][string]$Arguments)
    if ($CampaignBudget) {
        $campaign = [IO.File]::ReadAllText($CampaignBudget) | ConvertFrom-Json
        $remaining = Get-PnrStageRemainingSeconds $campaign
        if ($remaining -le 0) { throw 'Campaign deadline elapsed before native PDS stage' }
        $TimeoutSeconds = [Math]::Min($TimeoutSeconds, $remaining)
    }
    if (!('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
    }
    $stdout = $LogPrefix + '.stdout.log'
    $stderr = $LogPrefix + '.stderr.log'
    Write-Host "PDS_JOB owner_powershell_pid=$PID timeout_seconds=$TimeoutSeconds"
    Write-Host "PDS argv: $Arguments"
    Write-Host "PDS stdout: $stdout"
    Write-Host "PDS stderr: $stderr"
    Write-Host 'Timeout closes the whole Windows Job. To stop early, end this owner PowerShell process; Ctrl+C may be delayed during the native wait.'
    $savedPdsPython = $env:CPU_PDS_PYTHON
    $savedPdsPowerShell = $env:CPU_PDS_POWERSHELL
    try {
        $env:CPU_PDS_PYTHON = $PythonPath
        $env:CPU_PDS_POWERSHELL = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $exitCode = [CpuSimulation.BoundedProcess]::Run(
            $Executable, $Arguments, $Directory, $stdout, $stderr, $TimeoutSeconds)
    } catch {
        throw "PDS job stopped with its descendants: $($_.Exception.GetBaseException().Message); logs: $stdout / $stderr"
    } finally {
        $env:CPU_PDS_PYTHON = $savedPdsPython
        $env:CPU_PDS_POWERSHELL = $savedPdsPowerShell
    }
    if ($exitCode -ne 0) { throw "PDS failed: exit $exitCode; logs: $stdout / $stderr" }
    if ([IO.File]::ReadAllText($stdout) -match '(?m)^\s*E:\s' -or
        [IO.File]::ReadAllText($stderr) -match '(?m)^\s*E:\s') {
        throw "PDS reported an error despite exit 0; logs: $stdout / $stderr"
    }
}

function Invoke-CpuAdsCheck {
    param([string]$Netlist, [string]$Snapshot, [string]$Output, [string]$LogPrefix)
    if (!('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
    }
    $auditScript = Join-Path $PSScriptRoot 'audit_cpu_ads.py'
    $arguments = '"' + $auditScript + '" "' + $Netlist + '" --input-snapshot "' +
        $Snapshot + '" --output "' + $Output + '"'
    Write-Host 'CPU_ADS_CHECK bounded to 300 seconds; selected LUT cones, not whole-design gate simulation.'
    $exitCode = [CpuSimulation.BoundedProcess]::Run(
        $PythonPath, $arguments, $root, ($LogPrefix + '.stdout.log'), ($LogPrefix + '.stderr.log'), 300)
    if ($exitCode -ne 0) { throw "CPU ADS control audit failed: exit $exitCode; logs: $LogPrefix.*.log" }
    $result = [IO.File]::ReadAllText($Output) | ConvertFrom-Json
    if ($result.status -cne 'PASS') { throw 'CPU ADS audit did not produce a PASS result' }
    return $result
}

function Assert-FpgaSynthResources {
    param([string]$Report, [datetime]$StartedUtc)
    if (!(Test-Path -LiteralPath $Report -PathType Leaf) -or
        (Get-Item -LiteralPath $Report).LastWriteTimeUtc -lt $StartedUtc) {
        throw "Current-run ADS resource report is missing: $Report"
    }
    $body = [IO.File]::ReadAllText($Report)
    $patterns = [ordered]@{
        LUT = '(?m)^Total LUTs:\s*([0-9]+) of ([0-9]+)\s+\([0-9.]+%\)\r?$'
        FF = '(?m)^Total Registers:\s*([0-9]+) of ([0-9]+)\s+\([0-9.]+%\)\r?$'
        LUTRAM = '(?m)^\s*LUTs as dram:\s*([0-9]+) of ([0-9]+)\s+\([0-9.]+%\)\r?$'
        DRM = '(?m)^Total DRM =\s*([0-9.]+) of ([0-9]+)\s+\([0-9.]+%\)\r?$'
    }
    $counts = [ordered]@{}
    foreach ($label in $patterns.Keys) {
        $match = [regex]::Matches($body, $patterns[$label])
        if ($match.Count -ne 1) { throw "ADS resource count missing or ambiguous: $label" }
        $used = [decimal]::Parse($match[0].Groups[1].Value,
            [Globalization.CultureInfo]::InvariantCulture)
        $capacity = [decimal]::Parse($match[0].Groups[2].Value,
            [Globalization.CultureInfo]::InvariantCulture)
        if ($used -gt $capacity -or ($label -eq 'DRM' -and $used -gt 140)) {
            throw "ADS resource budget exceeded: $label=$used capacity=$capacity; DRM limit=140"
        }
        $counts[$label] = [pscustomobject][ordered]@{ used=$used; capacity=$capacity }
        Write-Host "ADS_RESOURCE_PASS $label=$used/$capacity"
    }
    if ([regex]::Matches($body, '(?m)^Total Latches:\s*0\s*$').Count -ne 1) {
        throw 'ADS resource gate requires exactly one zero-latch summary'
    }
    return [pscustomobject]$counts
}

function Invoke-FpgaCdcAdsCheck {
    param([string]$Python, [string]$Root, [string]$Vm, [string]$Adf,
        [string]$Ccr, [string]$Snapshot, [string]$Output, [string]$LogPrefix)
    $audit = Join-Path $Root 'pds/audit_cpu_sys_cdc_ads.py'
    $fdc = Join-Path $Root 'pds/soc.fdc'
    $argsText = '-B "' + $audit + '" --netlist "' + $Vm +
        '" --ccr "' + $Ccr + '" --adf "' + $Adf +
        '" --fdc "' + $fdc + '" --snapshot "' + $Snapshot +
        '" --output "' + $Output + '"'
    $stdout = $LogPrefix + '.stdout.log'
    $stderr = $LogPrefix + '.stderr.log'
    $code = [CpuSimulation.BoundedProcess]::Run($Python, $argsText, $Root,
        $stdout, $stderr, 300)
    if ($code -ne 0 -or !(Test-Path -LiteralPath $Output -PathType Leaf)) {
        throw "CPU/SYS ADS/CCR audit failed exit=$code; logs: $stdout / $stderr"
    }
    $result = [IO.File]::ReadAllText($Output) | ConvertFrom-Json
    $snapshotData = [IO.File]::ReadAllText($Snapshot) | ConvertFrom-Json
    if ($result.schema -ne 1 -or $result.status -cne 'PASS' -or
        $result.run_id -cne $snapshotData.run_id -or
        $result.snapshot_sha256 -cne (Get-FileHash -LiteralPath $Snapshot -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $result.vm_sha256 -cne (Get-FileHash -LiteralPath $Vm -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $result.adf_sha256 -cne (Get-FileHash -LiteralPath $Adf -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $result.ccr_sha256 -cne (Get-FileHash -LiteralPath $Ccr -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $result.fdc_sha256 -cne (Get-FileHash -LiteralPath $fdc -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $result.constraints.total_constraints -ne 1171 -or
        $result.constraints.cdc_directives -ne 48 -or
        $result.constraints.errors -ne 0 -or
        $result.constraints.critical_warnings -ne 39 -or
        $result.constraints.warnings -ne 0 -or @($result.fifos).Count -ne 10) {
        throw 'CPU/SYS ADS/CCR result lacks exact run, file, or constraint bindings'
    }
    Assert-FpgaCdcEvidenceRecords $result 'preflight'
    return $result
}

function Get-SdCellPort {
    param([string]$Ports, [string]$Name)
    $match = [regex]::Match($Ports, '(?ms)^\s*\.' + [regex]::Escape($Name) +
        '\s*\((?<value>.*?)\)\s*,?\s*$')
    if (!$match.Success) { throw "Synthesized SD RAM port missing: $Name" }
    return $match.Groups['value'].Value.Trim()
}

function Test-SdDynamicNet {
    param([string]$Value)
    # Strip Verilog numeric literals before looking for a connected signal.
    $withoutConstants = [regex]::Replace($Value,
        "(?i)\b\d*'[s]?[bodh][0-9a-f_xz?]+", '')
    $withoutConstants = [regex]::Replace($withoutConstants, '\b\d+\b', '')
    return $withoutConstants -match '[A-Za-z_\\]'
}

function Get-SdLogicDrivers {
    param([string]$ModuleText)
    $drivers = @{}
    $cellPattern = '(?ms)\bGTP_(?:LUT|MUX)[A-Z0-9]*\s*' +
        '(?:/\*.*?\*/\s*)?(?:#\s*\(.*?\)\s*)?\S+\s*\((?<ports>.*?)\);'
    foreach ($cell in [regex]::Matches($ModuleText, $cellPattern)) {
        $ports = $cell.Groups['ports'].Value
        $inputs = @([regex]::Matches($ports,
            '(?m)^\s*\.(?:I\d+|S|CIN)\s*\((?<net>.*?)\)\s*,?\s*$') |
            ForEach-Object { $_.Groups['net'].Value.Trim() })
        foreach ($output in [regex]::Matches($ports,
            '(?m)^\s*\.(?:Z|Z5|COUT)\s*\((?<net>.*?)\)\s*,?\s*$')) {
            $net = $output.Groups['net'].Value.Trim()
            if ($net -and !$drivers.ContainsKey($net)) { $drivers[$net] = $inputs }
        }
    }
    return $drivers
}

function Test-SdNetDepends {
    param([hashtable]$Drivers, [string]$Start,
        [string]$TargetPattern, [int]$MaxDepth = 4)
    $front = @($Start)
    $visited = [Collections.Generic.HashSet[string]]::new()
    for ($depth = 0; $depth -le $MaxDepth; $depth++) {
        $next = [Collections.Generic.List[string]]::new()
        foreach ($net in $front) {
            if ($net -match $TargetPattern) { return $true }
            if (!$visited.Add($net) -or !$Drivers.ContainsKey($net)) { continue }
            foreach ($inputNet in $Drivers[$net]) { $next.Add($inputNet) }
        }
        $front = @($next)
    }
    return $false
}

function Assert-SdSectorRamStorage {
    param([string]$NetlistText, [string]$FlowLogText)

    if ($FlowLogText -match '(?mi)^\s*W:\s*Sdm-2010:') {
        throw 'PDS reported Sdm-2010 unsupported simultaneous RAM writers'
    }
    $sdStart = $NetlistText.IndexOf('module sd_native_mmio',
        [StringComparison]::Ordinal)
    if ($sdStart -lt 0) { throw 'Synthesized SD controller module missing' }
    $sdEnd = $NetlistText.IndexOf('endmodule', $sdStart,
        [StringComparison]::Ordinal)
    if ($sdEnd -lt 0) { throw 'Synthesized SD controller is incomplete' }
    $sdText = $NetlistText.Substring($sdStart, $sdEnd - $sdStart)
    $sdHeaderEnd = $sdText.IndexOf(');')
    if ($sdHeaderEnd -lt 0) { throw 'Synthesized SD controller has no port header' }
    $sdOutputs = [Collections.Generic.HashSet[string]]::new()
    foreach ($output in [regex]::Matches(
            $sdText.Substring(0, $sdHeaderEnd + 2),
            '(?m)^\s*output(?:\s+\[\d+:\d+\])?\s+(?<net>\S+?)\s*[,)]')) {
        [void]$sdOutputs.Add($output.Groups['net'].Value.Trim())
    }
    $sdDrivers = Get-SdLogicDrivers $sdText
    $ramPattern = '(?ms)\bGTP_RAM(?<depth>64|128)X1DP\s*/\*\s*(?<name>[^*\r\n]+?)\s*\*/' +
        '\s*#\s*\(.*?\)\s*\S+\s*\((?<ports>.*?)\);'
    $readConsumers = [Collections.Generic.HashSet[string]]::new()
    foreach ($consumer in [regex]::Matches($sdText,
        '(?m)^\s*\.I\d+\s*\((?<net>.*?)\)\s*(?:,|\)\s*;)?\s*$')) {
        [void]$readConsumers.Add($consumer.Groups['net'].Value.Trim())
    }
    $bankPorts = @{}
    $bankTxOutputs = @{}
    $bankCpuOutputs = @{}

    foreach ($bank in 0..1) {
        $instance = [regex]::Match($sdText,
            '(?ms)^\s*(?<type>sd_native_sector_bank(?:_unq\d+)?)\s+u_buffer' +
            $bank + '\s*\((?<ports>.*?)\);')
        if (!$instance.Success) {
            throw "Synthesized SD buffer$bank sector bank instance missing"
        }
        $type = $instance.Groups['type'].Value
        $module = [regex]::Match($NetlistText,
            '(?m)^module\s+' + [regex]::Escape($type) + '\s*$')
        if (!$module.Success) { throw "Synthesized SD bank module missing: $type" }
        $moduleEnd = $NetlistText.IndexOf('endmodule', $module.Index,
            [StringComparison]::Ordinal)
        if ($moduleEnd -lt 0) { throw "Synthesized SD bank module incomplete: $type" }
        $sectorText = $NetlistText.Substring($module.Index,
            $moduleEnd - $module.Index)
        $headerEnd = $sectorText.IndexOf(');')
        if ($headerEnd -lt 0) { throw "Synthesized SD bank has no port header: $type" }
        $moduleHeader = $sectorText.Substring(0, $headerEnd + 2)
        $moduleOutputs = [Collections.Generic.HashSet[string]]::new()
        foreach ($output in [regex]::Matches($moduleHeader,
            '(?m)^\s*output(?:\s+\[\d+:\d+\])?\s+(?<net>\S+?)\s*[,)]')) {
            [void]$moduleOutputs.Add($output.Groups['net'].Value.Trim())
        }

        $bankPorts[$bank] = @{}
        # ADS may absorb buffer0's CPU ownership expression into the sector
        # bank while leaving buffer1's expression at the parent boundary.
        # Audit the surviving inputs and their guard cone in that shape.
        $optimizedCpu0 = $bank -eq 0 -and
            !$instance.Groups['ports'].Value.Contains('.\u_sd/cpu_write0')
        $flattenedGuard = if ($bank -eq 0) { '_N328773' } else { '_N328779' }
        $hasFlattenedGuard = $instance.Groups['ports'].Value.Contains(
            '.' + $flattenedGuard + ' (')
        if ($hasFlattenedGuard) {
            # Some valid ADS mappings flatten this owner path into soc_top.
            # Check that specific mapping only when the explicit port vanished.
            $flattenedWritePos = $NetlistText.IndexOf('.Z (_N292376)',
                [StringComparison]::Ordinal)
            if ($flattenedWritePos -lt 0) {
                throw 'Synthesized SD flattened write source missing'
            }
            $flattenedWriteEnd = $NetlistText.IndexOf(');', $flattenedWritePos,
                [StringComparison]::Ordinal)
            if ($flattenedWriteEnd -lt 0 -or $flattenedWriteEnd - $flattenedWritePos -gt 600) {
                throw 'Synthesized SD flattened write source malformed'
            }
            $flattenedWriteCell = $NetlistText.Substring($flattenedWritePos,
                $flattenedWriteEnd - $flattenedWritePos)
            foreach ($input in @('.I0 (io_wr)', '.I3 (\u_sd/busy_rnmt )',
                    '.I4 (\u_sd/write_multi_active_rnmt )')) {
                if (!$flattenedWriteCell.Contains($input)) {
                    throw "Synthesized SD flattened write source lacks $input"
                }
            }
        }
        foreach ($port in @('write_addr','write_data','cpu_read_addr',
                'tx_read_addr','l_wstrb','clk')) {
            $value = Get-SdCellPort $instance.Groups['ports'].Value $port
            if (!(Test-SdDynamicNet $value)) {
                throw "Synthesized SD buffer$bank has constant/disconnected $port"
            }
            $bankPorts[$bank][$port] = $value
        }
        foreach ($owner in @('cpu_write','rx_write')) {
            if ($optimizedCpu0 -and $owner -eq 'cpu_write') {
                foreach ($pair in @(
                    @('io_wr','wr'),
                    @('\u_sd/normal_path','normal_path'),
                    @('\u_sd/N215','N215'),
                    @('_N328773','_N328773'),
                    @('_N292376','_N292376')
                )) {
                    if ((Get-SdCellPort $instance.Groups['ports'].Value $pair[0]) -cne $pair[1]) {
                        throw "Synthesized SD buffer0 flattened CPU ownership input changed: $($pair[0])"
                    }
                }
                if (!(Test-SdNetDepends $sdDrivers '_N328773' '^tx0_full$' 2)) {
                    throw 'Synthesized SD buffer0 flattened CPU write lacks tx0_full guard'
                }
                $bankPorts[$bank][$owner] = 'wr'
                continue
            }
            $ownerPort = '\u_sd/' + $owner + $bank
            $value = Get-SdCellPort $instance.Groups['ports'].Value $ownerPort
            if ($value -cne ($owner + $bank)) {
                throw "Synthesized SD buffer$bank lost $owner ownership input"
            }
            $bankPorts[$bank][$owner] = $value
        }
        if (!$optimizedCpu0 -and
                !(Test-SdNetDepends $sdDrivers ('cpu_write' + $bank) `
                    ('^tx' + $bank + '_full$') 4)) {
            throw "Synthesized SD buffer$bank CPU write lacks tx$bank`_full guard"
        }

        $ramCells = [regex]::Matches($sectorText, $ramPattern)
        if ($ramCells.Count -ne [regex]::Matches($sectorText,
                '\bGTP_RAM\d+X1DP\b').Count) {
            throw "Unsupported or unparsed RAM primitive in synthesized SD buffer$bank"
        }
        $views = @{
            cpu = [Collections.Generic.Dictionary[string,object]]::new()
            tx = [Collections.Generic.Dictionary[string,object]]::new()
        }
        $bankCpuOutputs[$bank] = [Collections.Generic.HashSet[string]]::new()
        $bankTxOutputs[$bank] = [Collections.Generic.HashSet[string]]::new()
        foreach ($cell in $ramCells) {
            $name = $cell.Groups['name'].Value.Trim()
            if ($name -notmatch '(?:^|[\\/._])(?<view>cpu|tx)_mem(?:[\\/._\[]|$)') {
                throw "Unexpected RAM in synthesized SD buffer$bank`: $name"
            }
            $view = $Matches['view']
            # PDS repeats cpu_mem_0_0 in each generated byte lane.
            $suffix = $name -creplace '(cpu|tx)_mem', 'mem'
            if ($views[$view].ContainsKey($suffix)) {
                throw "Duplicate synthesized SD buffer$bank $view RAM slice: $suffix"
            }
            $ports = @{}
            foreach ($port in @('RADDR','WADDR','DO','DI','WCLK','WE')) {
                $ports[$port] = Get-SdCellPort $cell.Groups['ports'].Value $port
                if (!(Test-SdDynamicNet $ports[$port])) {
                    throw "Synthesized SD buffer$bank $view RAM $name has constant/disconnected $port"
                }
            }
            if ($ports['RADDR'] -notmatch ($view + '_read_addr')) {
                throw "Synthesized SD buffer$bank $view RAM lacks its read address"
            }
            $output = $ports['DO']
            if (!$moduleOutputs.Contains($output)) {
                throw "Synthesized SD buffer$bank $view RAM output is not exported: $name"
            }
            $parentOutput = Get-SdCellPort $instance.Groups['ports'].Value $output
            if (!(Test-SdDynamicNet $parentOutput) -or
                    (!$readConsumers.Contains($parentOutput) -and
                    !$sdOutputs.Contains($parentOutput))) {
                throw "Synthesized SD buffer$bank $view RAM read output is unused: $name"
            }
            if ($view -eq 'cpu') { [void]$bankCpuOutputs[$bank].Add($parentOutput) }
            else { [void]$bankTxOutputs[$bank].Add($parentOutput) }
            $views[$view].Add($suffix, @{
                depth = [int]$cell.Groups['depth'].Value
                ports = $ports
            })
        }
        foreach ($view in @('cpu','tx')) {
            $capacity = 0
            foreach ($cell in $views[$view].Values) { $capacity += $cell['depth'] }
            if ($capacity -ne 4096) {
                throw "Incomplete SD buffer$bank $view mirror: $capacity/4096 RAM bits"
            }
        }
        if ($bankCpuOutputs[$bank].Overlaps($bankTxOutputs[$bank])) {
            throw "Synthesized SD buffer$bank CPU/TX read outputs are merged"
        }
        $matchingPacking = $views['cpu'].Count -eq $views['tx'].Count
        foreach ($suffix in $views['cpu'].Keys) {
            if (!$views['tx'].ContainsKey($suffix) -or
                    $views['cpu'][$suffix]['depth'] -ne
                        $views['tx'][$suffix]['depth']) {
                $matchingPacking = $false
                break
            }
        }
        if ($matchingPacking) {
            foreach ($suffix in $views['cpu'].Keys) {
                $cpu = $views['cpu'][$suffix]['ports']
                $tx = $views['tx'][$suffix]['ports']
                foreach ($port in @('WADDR','DI','WCLK','WE')) {
                    if ($cpu[$port] -cne $tx[$port]) {
                        throw "SD buffer$bank RAM mirrors disagree on $port at slice $suffix"
                    }
                }
            }
        } else {
            foreach ($port in @('DI','WCLK')) {
                $cpuSources = [Collections.Generic.HashSet[string]]::new()
                $txSources = [Collections.Generic.HashSet[string]]::new()
                foreach ($cell in $views['cpu'].Values) {
                    [void]$cpuSources.Add($cell['ports'][$port])
                }
                foreach ($cell in $views['tx'].Values) {
                    [void]$txSources.Add($cell['ports'][$port])
                }
                if (!$cpuSources.SetEquals($txSources)) {
                    throw "SD buffer$bank RAM mirrors disagree on $port sources"
                }
            }
        }
        $sectorDrivers = Get-SdLogicDrivers $sectorText
        if ($hasFlattenedGuard) {
            if (!(Test-SdNetDepends $sdDrivers $flattenedGuard `
                    ('^tx' + $bank + '_full$') 2)) {
                throw "SD buffer$bank flattened CPU guard lacks TX-full ownership"
            }
        }
        $writeEnableNets = [Collections.Generic.HashSet[string]]::new()
        foreach ($view in @('cpu','tx')) {
            foreach ($cell in $views[$view].Values) {
                [void]$writeEnableNets.Add($cell['ports']['WE'])
            }
        }
        foreach ($enable in $writeEnableNets) {
            foreach ($owner in @('cpu_write','rx_write')) {
                $ownerNet = '\u_sd/' + $owner + $bank
                $directOwner = Test-SdNetDepends $sectorDrivers $enable `
                    ('^' + [regex]::Escape($ownerNet) + '$') 3
                $flattenedOwner = $hasFlattenedGuard -and $owner -eq 'cpu_write' -and
                    (Test-SdNetDepends $sectorDrivers $enable `
                        ('^' + [regex]::Escape($flattenedGuard) + '$') 7) -and
                    (Test-SdNetDepends $sectorDrivers $enable '^_N292376$' 7)
                if (!$directOwner -and !$flattenedOwner) {
                    throw "SD buffer$bank RAM write enable lacks $owner source: $enable"
                }
            }
            if (!(Test-SdNetDepends $sectorDrivers $enable '^l_wstrb\[\d\]$' 3)) {
                throw "SD buffer$bank RAM write enable lacks byte strobe: $enable"
            }
        }
    }
    foreach ($port in @('write_addr','write_data','cpu_write','rx_write')) {
        if ($bankPorts[0][$port] -ceq $bankPorts[1][$port]) {
            throw "Synthesized SD buffer0/buffer1 share $port"
        }
    }
    if ($bankCpuOutputs[0].Overlaps($bankCpuOutputs[1]) -or
            $bankTxOutputs[0].Overlaps($bankTxOutputs[1])) {
        throw 'Synthesized SD buffer0/buffer1 read outputs are merged'
    }
    foreach ($bit in 0..31) {
        $net = 'write_word[' + $bit + ']'
        if (!$sdDrivers.ContainsKey($net)) {
            throw "Synthesized SD TX read mux missing bit $bit"
        }
        $inputs = [Collections.Generic.HashSet[string]]::new()
        foreach ($inputNet in $sdDrivers[$net]) { [void]$inputs.Add($inputNet) }
        if (!$inputs.Contains('write_buffer_select') -or
                !$inputs.Overlaps($bankTxOutputs[0]) -or
                !$inputs.Overlaps($bankTxOutputs[1])) {
            throw "Synthesized SD TX read mux bit $bit lacks bank selection/data"
        }
    }
    return @{
        0 = 'CPU+TX mirrored distributed RAM, 4096 bits/view'
        1 = 'CPU+TX mirrored distributed RAM, 4096 bits/view'
    }
}

function Assert-SdWriteCommandPath {
    param([string]$NetlistText)
    $start = $NetlistText.IndexOf('module sd_native_mmio',
        [StringComparison]::Ordinal)
    if ($start -lt 0) { throw 'Synthesized SD controller module missing' }
    $end = $NetlistText.IndexOf('endmodule', $start,
        [StringComparison]::Ordinal)
    if ($end -lt 0) { throw 'Synthesized SD controller module incomplete' }
    $moduleText = $NetlistText.Substring($start, $end - $start)
    $drivers = Get-SdLogicDrivers $moduleText

    # ADS maps this non-reset register to bare GTP_DFF, not GTP_DFF_*.
    $latch = [regex]::Match($moduleText,
        '(?ms)\bGTP_DFF(?:_\w+)?\s*/\*\s*cmd_write_latched\s*\*/' +
        '\s*#\(.*?\)\s*\S+\s*\((?<ports>.*?)\);')
    if (!$latch.Success) { throw 'Synthesized SD write-command latch missing' }
    $latchPorts = $latch.Groups['ports'].Value
    if ((Get-SdCellPort $latchPorts 'Q') -cne 'cmd_write_latched' -or
            (Get-SdCellPort $latchPorts 'CLK') -cne 'clk') {
        throw 'Synthesized SD write-command latch output/clock changed'
    }
    $latchData = Get-SdCellPort $latchPorts 'D'
    if (!(Test-SdDynamicNet $latchData) -or
            !(Test-SdNetDepends $drivers $latchData '^l_wdata\[12\]$' 3) -or
            !(Test-SdNetDepends $drivers $latchData '^cmd_write_latched$' 3)) {
        throw 'Synthesized SD write-command latch lacks command bit/hold path'
    }

    $multi = [regex]::Match($moduleText,
        '(?ms)\bGTP_DFF(?:_\w+)?\s*/\*\s*write_multi_active\s*\*/' +
        '\s*#\(.*?\)\s*\S+\s*\((?<ports>.*?)\);')
    if (!$multi.Success -or
            (Get-SdCellPort $multi.Groups['ports'].Value 'Q') -cne
                'write_multi_active') {
        throw 'Synthesized SD CMD25 mode latch missing'
    }
    $multiData = Get-SdCellPort $multi.Groups['ports'].Value 'D'
    foreach ($bit in @(10,12)) {
        if (!(Test-SdNetDepends $drivers $multiData `
                ('^l_wdata\[' + $bit + '\]$') 4)) {
            throw "Synthesized SD CMD25 mode lacks command bit $bit"
        }
    }
    $writeStateCount = 0
    $multiStateCount = 0
    foreach ($state in [regex]::Matches($moduleText,
        '(?ms)\bGTP_DFF(?:_\w+)?\s*/\*\s*\\state_reg\[\d+\]' +
        '\s*\*/\s*#\(.*?\)\s*\S+\s*\((?<ports>.*?)\);')) {
        $nextState = Get-SdCellPort $state.Groups['ports'].Value 'D'
        if (Test-SdNetDepends $drivers $nextState '^cmd_write_latched$' 5) {
            $writeStateCount++
            if (Test-SdNetDepends $drivers $nextState '^write_multi_active$' 5) {
                $multiStateCount++
            }
        }
    }
    if ($writeStateCount -lt 2 -or $multiStateCount -lt 1) {
        throw 'Synthesized SD CMD24/CMD25 next-state paths are missing'
    }
    return "CMD24/CMD25 write latch and next-state cones verified ($writeStateCount/$multiStateCount)"
}

if ($CheckSdStorageOnly) {
    if ($FinalizeCompletedBuild) { throw 'Choose one build-check mode' }
    $netlistPath = Join-Path $root 'pds/synthesize/soc_top_syn.vm'
    $flowPath = Join-Path $root 'pds/flow.log'
    $rtlPath = Join-Path $root 'rtl/soc/sd_native_mmio.v'
    foreach ($path in @($netlistPath,$flowPath)) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing PDS evidence: $path" }
        if ((Get-Item -LiteralPath $path).LastWriteTimeUtc -lt
                (Get-Item -LiteralPath $rtlPath).LastWriteTimeUtc) {
            throw "PDS evidence predates current SD RTL: $path"
        }
    }
    $netlistText = [IO.File]::ReadAllText($netlistPath)
    $storage = Assert-SdSectorRamStorage $netlistText `
        (Get-Content -LiteralPath $flowPath -Raw)
    $writePath = Assert-SdWriteCommandPath $netlistText
    Write-Output "SD_SECTOR_RAM_SYNTH_PASS $($storage[0]); $($storage[1])"
    Write-Output "SD_WRITE_COMMAND_SYNTH_PASS $writePath"
    return
}

# Resolve this prerequisite before starting a potentially long PDS flow.
if (!$PythonPath) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (!$pythonCommand) { throw 'CPU ADS audit requires Python 3. Pass -PythonPath or add python to PATH.' }
    $PythonPath = $pythonCommand.Source
}
if (!(Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Missing Python executable: $PythonPath" }
$PythonPath = [IO.Path]::GetFullPath($PythonPath)
if (!('CpuSimulation.BoundedProcess' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
}
$cpuPythonLogs = Join-Path $root 'artifacts/selftest'
New-Item -ItemType Directory -Path $cpuPythonLogs -Force | Out-Null
$cpuPythonStatus = [CpuSimulation.BoundedProcess]::Run($PythonPath,
    '-c "import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3, 8) else 2)"',
    $root, (Join-Path $cpuPythonLogs 'cpu-ads-python.stdout.log'),
    (Join-Path $cpuPythonLogs 'cpu-ads-python.stderr.log'), 10)
if ($cpuPythonStatus -ne 0) { throw "CPU ADS audit requires working Python 3.8 or newer; logs: $cpuPythonLogs/cpu-ads-python.*.log" }

if ($FinalizeCompletedBuild) {
    if ($BuildStartedUtc -eq [datetime]::MinValue) { throw 'Finalize requires the original build start UTC' }
    $pds = Join-Path $root 'pds'
    # A finalization may only resume the exact recorded start, never create a
    # new fingerprint for an older bitstream. This also checks the saved bytes.
    $buildSnapshot = Read-FpgaActiveSnapshot $root $BuildStartedUtc
    $pdsStartedUtc = [datetime]::Parse($buildSnapshot.started_utc).ToUniversalTime()
    $runDir = Join-Path $pds ('input-snapshots/' + $buildSnapshot.run_id)
    Assert-FpgaStageHistory (Join-Path $runDir 'synth.impl.tcl') 'synthesis'
    Assert-FpgaStageHistory (Join-Path $pds 'impl.tcl') 'post_synthesis'
} else {
if (!$PdsShell) {
    $candidates = @(
        'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe',
        'D:\LJL\WORK\pango\PDS_2022.2-SP6.4\bin\pds_shell.exe'
    )
    if ($env:PDS_ROOT) {
        $candidates = @((Join-Path $env:PDS_ROOT 'bin\pds_shell.exe')) +
            $candidates
    }
    $candidates = $candidates | Where-Object {
        $_ -and (Test-Path -LiteralPath $_)
    }
    $PdsShell = $candidates | Select-Object -First 1
}
if (!$PdsShell -or !(Test-Path -LiteralPath $PdsShell -PathType Leaf)) {
    throw 'Missing PDS. Pass -PdsShell or set PDS_ROOT.'
}
$PdsShell = [IO.Path]::GetFullPath($PdsShell)

. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$recipeInputs = Get-FpgaHashMap $root (Get-FpgaRecipeInputPaths $root -AllowHdmiRegeneration:$RebuildHdmiAssets)
$cpuOriginalPath = $env:PATH
try {
if ($UseExistingFirmware) {
    # CPU/RTL-only candidates may reuse the exact release firmware bytes when
    # the recorded ELF/BIN metadata and the consumed ROM all still agree.
    Assert-FpgaFirmware $root
    Write-Output 'FPGA_EXISTING_FIRMWARE_VERIFIED'
} else {
$nativeToolchain = (Get-CpuToolchain -ToolchainRoot $ToolchainRoot).Root
& (Join-Path $PSScriptRoot 'build_bootloader.ps1') -ToolchainRoot $nativeToolchain
if ($LASTEXITCODE -ne 0) { throw 'Bootloader build failed' }
& (Join-Path $PSScriptRoot 'build_mac_selftest_wsl.ps1') `
    -Distro $Distro -ToolchainRoot $nativeToolchain
if ($LASTEXITCODE -ne 0) { throw 'MAC self-test build failed' }
& (Join-Path $PSScriptRoot 'build_mac_benchmark_wsl.ps1') `
    -Distro $Distro -ToolchainRoot $nativeToolchain
if ($LASTEXITCODE -ne 0) { throw 'MAC benchmark build failed' }
& (Join-Path $PSScriptRoot 'build_xiangqi_sparse_eval_wsl.ps1') `
    -Distro $Distro -ToolchainRoot $nativeToolchain
if ($LASTEXITCODE -ne 0) {
    throw 'Xiangqi sparse evaluator self-test build failed'
}
& (Join-Path $PSScriptRoot 'build_xiangqi_fb_demo_wsl.ps1') `
    -Distro $Distro -ToolchainRoot $nativeToolchain
if ($LASTEXITCODE -ne 0) { throw 'Xiangqi framebuffer demo build failed' }
if ($RebuildHdmiAssets) {
    & (Join-Path $PSScriptRoot 'gen_hdmi_header.ps1')
}
}

} finally {
    $env:PATH = $cpuOriginalPath
}
Assert-FpgaMap $recipeInputs (Get-FpgaHashMap $root (Get-FpgaRecipeInputPaths $root -AllowHdmiRegeneration:$RebuildHdmiAssets)) 'Inputs changed during firmware build'

$pds = Join-Path $root 'pds'
$projectText = [IO.File]::ReadAllText((Join-Path $pds 'soc.tcl'))
foreach ($source in @('../rtl/audio/audio_mmio.v', '../rtl/audio/i2s_audio_duplex.v')) {
    if (!$projectText.Contains("add_design `"$source`"")) {
        throw "PDS project is missing audio source: $source"
    }
}
Copy-Item -LiteralPath (Join-Path $root 'rtl\video\font8x16.hex') `
    -Destination (Join-Path $pds 'font8x16.hex') -Force
Copy-Item -LiteralPath (Join-Path $root 'rtl\video\header_bitmap.hex') `
    -Destination (Join-Path $pds 'header_bitmap.hex') -Force
Copy-Item -LiteralPath (Join-Path $root 'rtl\video\header_logo_rgb332.hex') `
    -Destination (Join-Path $pds 'header_logo_rgb332.hex') -Force
& (Join-Path $PSScriptRoot 'prepare_pds_project.ps1')
$implHistory = Join-Path $pds 'impl.tcl'
$buildSnapshot = New-FpgaSnapshot $root
$pdsStartedUtc = [datetime]::Parse($buildSnapshot.started_utc).ToUniversalTime()
Write-Output "FPGA_INPUTS_FROZEN run=$($buildSnapshot.run_id) started_utc=$($buildSnapshot.started_utc)"
$runDir = Join-Path $pds ('input-snapshots/' + $buildSnapshot.run_id)
$hadImplHistory = Test-Path -LiteralPath $implHistory -PathType Leaf
$savedImplHistory = $null
if ($hadImplHistory) {
    $savedImplHistory = [IO.File]::ReadAllBytes($implHistory)
    Remove-Item -LiteralPath $implHistory -Force
}
Push-Location $pds
$pdsSucceeded = $false
try {
    # Stage 1 creates an RTL project and stops after ADS. The next project is
    # post-synthesis and imports this exact audited ADF without rerunning ADS.
    Invoke-FpgaPdsJob -Executable $PdsShell -Directory $pds -LogPrefix (Join-Path $runDir 'pds.parse-synth') -TimeoutSeconds 120 -Arguments '-parsetcl soc.tcl soc_pre_synth.pds -model 3'
    Invoke-FpgaPdsJob -Executable $PdsShell -Directory $pds -LogPrefix (Join-Path $runDir 'pds.synth') -TimeoutSeconds $PdsTimeoutSeconds -Arguments '-project soc_pre_synth.pds -run synthesize'
    Assert-FpgaStageHistory $implHistory 'synthesis'
    Copy-Item -LiteralPath $implHistory -Destination (Join-Path $runDir 'synth.impl.tcl')
    $preProject = Join-Path $pds 'soc_pre_synth.pds'
    if (!(Test-Path -LiteralPath $preProject -PathType Leaf) -or
        (Get-Item -LiteralPath $preProject).LastWriteTimeUtc -lt $pdsStartedUtc) {
        throw 'Fresh native synthesis project is missing'
    }
    Copy-Item -LiteralPath $preProject -Destination (Join-Path $runDir 'soc_pre_synth.pds')
    foreach ($relative in @('synthesize/soc_top.snr','synthesize/soc_top_syn.vm',
            'synthesize/soc_top_syn.adf','constraint_check/constraint_check.ccr','flow.log')) {
        $path = Join-Path $pds $relative
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).LastWriteTimeUtc -lt $pdsStartedUtc) {
            throw "Fresh synthesis output is missing: $path"
        }
    }
    Copy-Item -LiteralPath (Join-Path $pds 'flow.log') -Destination (Join-Path $runDir 'synth.flow.log')
    Copy-Item -LiteralPath (Join-Path $pds 'constraint_check/constraint_check.ccr') -Destination (Join-Path $runDir 'synth.constraint_check.ccr')
    $synthSnr = Join-Path $pds 'synthesize/soc_top.snr'
    $synthVm = Join-Path $pds 'synthesize/soc_top_syn.vm'
    $synthAdf = Join-Path $pds 'synthesize/soc_top_syn.adf'
    $synthCcr = Join-Path $runDir 'synth.constraint_check.ccr'
    $resources = Assert-FpgaSynthResources $synthSnr $pdsStartedUtc
    & (Join-Path $PSScriptRoot 'build_cpu_ads_gate.ps1') -PythonPath $PythonPath -ProjectRoot $root -EvidenceDirectory $runDir
    $cpuPrePath = Join-Path $runDir 'cpu-pre-pnr.json'
    $icachePrePath = Join-Path $runDir 'icache-pad-pre-pnr.json'
    $cdcPrePath = Join-Path $runDir 'cpu-sys-cdc-ads.json'
    $cdcResult = Invoke-FpgaCdcAdsCheck -Python $PythonPath -Root $root -Vm $synthVm -Adf $synthAdf -Ccr $synthCcr -Snapshot (Join-Path $pds 'build_snapshot.json') -Output $cdcPrePath -LogPrefix (Join-Path $runDir 'cpu-sys-cdc-pre-pnr')
    $snapshotHash = (Get-FileHash -LiteralPath (Join-Path $pds 'build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $synthHashes = [ordered]@{
        'pds/synthesize/soc_top.snr' = (Get-FileHash -LiteralPath $synthSnr -Algorithm SHA256).Hash.ToLowerInvariant()
        'pds/synthesize/soc_top_syn.vm' = (Get-FileHash -LiteralPath $synthVm -Algorithm SHA256).Hash.ToLowerInvariant()
        'pds/synthesize/soc_top_syn.adf' = (Get-FileHash -LiteralPath $synthAdf -Algorithm SHA256).Hash.ToLowerInvariant()
        ('pds/input-snapshots/' + $buildSnapshot.run_id + '/synth.constraint_check.ccr') = (Get-FileHash -LiteralPath $synthCcr -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $preflight = [ordered]@{
        schema = 1; status = 'PASS'; run_id = $buildSnapshot.run_id
        input_snapshot_sha256 = $snapshotHash; pds = '2022.2-SP6.4'
        parse_argv = '-parsetcl soc.tcl soc_pre_synth.pds -model 3'
        synth_argv = '-project soc_pre_synth.pds -run synthesize'
        post_parse_argv = '-parsetcl soc_post_synth.tcl soc.pds -model 3'
        post_route_argv = '-project soc.pds -run gen_bit_stream'
        resources = $resources; synth_hashes = $synthHashes
        cdc_summary = [ordered]@{
            total_constraints = $cdcResult.constraints.total_constraints
            errors = $cdcResult.constraints.errors
            critical_warnings = $cdcResult.constraints.critical_warnings
            warnings = $cdcResult.constraints.warnings
            mapped_directions = @($cdcResult.fifos).Count
            payload_ram_cells = (@($cdcResult.payloads | Measure-Object -Property mapped_ram_cells -Sum)[0]).Sum
            payload_do_outputs = (@($cdcResult.payloads | Measure-Object -Property mapped_do_outputs -Sum)[0]).Sum
            first_stage_crossings = @($cdcResult.first_stage_crossings).Count
            vector_match_each = 1; mapped_ff_each = 5
        }
        cpu_ads_sha256 = (Get-FileHash -LiteralPath $cpuPrePath -Algorithm SHA256).Hash.ToLowerInvariant()
        icache_ads_sha256 = (Get-FileHash -LiteralPath $icachePrePath -Algorithm SHA256).Hash.ToLowerInvariant()
        cdc_ads_sha256 = (Get-FileHash -LiteralPath $cdcPrePath -Algorithm SHA256).Hash.ToLowerInvariant()
        synth_history_sha256 = (Get-FileHash -LiteralPath (Join-Path $runDir 'synth.impl.tcl') -Algorithm SHA256).Hash.ToLowerInvariant()
        synth_project_sha256 = (Get-FileHash -LiteralPath (Join-Path $runDir 'soc_pre_synth.pds') -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $preflightPath = Join-Path $runDir 'preflight_gate.json'
    if ((Get-Content -LiteralPath (Join-Path $root 'rtl/cpu/CoreTop.sv') -Raw).Contains('io_shiftSrcPrepared')) {
        $preflight.prepared_shift_ads_sha256 = (Get-FileHash -LiteralPath (Join-Path $runDir 'prepared-shift-pre-pnr.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if((Get-SocCpuClockMode (Get-Content -LiteralPath (Join-Path $root 'config/clocks.json') -Raw|ConvertFrom-Json)) -ne 0){
        $clockGatePath=Join-Path $runDir 'cpu-clock-pre-pnr.json'
        $preflight.cpu_clock_ads_sha256=(Get-FileHash -LiteralPath $clockGatePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if (Test-Path -LiteralPath $preflightPath) { throw 'Preflight gate already exists for this run' }
    [IO.File]::WriteAllText($preflightPath, ($preflight | ConvertTo-Json -Depth 7) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    $null = Read-FpgaActiveSnapshot $root $pdsStartedUtc
    Write-Output "SOC_ADS_PREFLIGHT_PASS run=$($buildSnapshot.run_id) adf=$($synthHashes['pds/synthesize/soc_top_syn.adf'])"

    if ($SynthesisOnly) {
        $receipt = [ordered]@{
            schema = 1; status = 'SYNTHESIS_ONLY_PASS_NOT_TIMING_OR_BOARD_ACCEPTANCE'
            run_id = $buildSnapshot.run_id; pnr_started = $false
            input_snapshot_sha256 = $snapshotHash
            preflight_sha256 = (Get-FileHash -LiteralPath $preflightPath -Algorithm SHA256).Hash.ToLowerInvariant()
            resources = $resources; completed_utc = [DateTime]::UtcNow.ToString('o')
        }
        [IO.File]::WriteAllText((Join-Path $runDir 'synthesis-only.json'),
            ($receipt | ConvertTo-Json -Depth 7) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        $pdsSucceeded = $true
        Write-Output "SOC_SYNTHESIS_ONLY_PASS run=$($buildSnapshot.run_id) PNR_NOT_STARTED"
        return
    }

    # Keep separate native histories, never a fabricated concatenation.
    Remove-Item -LiteralPath $implHistory -Force
    Invoke-FpgaPdsJob -Executable $PdsShell -Directory $pds -LogPrefix (Join-Path $runDir 'pds.parse-post') -TimeoutSeconds 120 -Arguments '-parsetcl soc_post_synth.tcl soc.pds -model 3'
    $postProject = Join-Path $pds 'soc.pds'
    if (!(Test-Path -LiteralPath $postProject -PathType Leaf) -or
        (Get-Item -LiteralPath $postProject).LastWriteTimeUtc -lt $pdsStartedUtc) {
        throw 'Fresh native post-synthesis project is missing'
    }
    Copy-Item -LiteralPath $postProject -Destination (Join-Path $runDir 'soc_post_synth.before_route.pds')
    if (!(Test-Path -LiteralPath $preProject -PathType Leaf) -or
        (Get-FileHash -LiteralPath $preProject -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            $preflight.synth_project_sha256) {
        throw 'Post-project parse changed the audited synthesis project before route'
    }
    foreach ($relative in @('pds/synthesize/soc_top.snr','pds/synthesize/soc_top_syn.vm',
            'pds/synthesize/soc_top_syn.adf')) {
        $path = Join-Path $root $relative
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $synthHashes[$relative]) {
            throw "Post-project parse changed audited ADS bytes before route: $relative"
        }
    }
    if ($CampaignBudget) {
        Register-PnrAttempt -Path $CampaignBudget -RunId $buildSnapshot.run_id -Purpose $AttemptPurpose -SnapshotPath (Join-Path $pds 'build_snapshot.json')
        $campaign = Get-Content -LiteralPath $CampaignBudget -Raw -Encoding UTF8 | ConvertFrom-Json
        $remaining = Get-PnrStageRemainingSeconds $campaign
        if ($remaining -le 0) { throw 'Campaign expired after launch reservation; attempt remains counted' }
        $PdsTimeoutSeconds = [Math]::Min($PdsTimeoutSeconds, $remaining)
    }
    Invoke-FpgaPdsJob -Executable $PdsShell -Directory $pds -LogPrefix (Join-Path $runDir 'pds') -TimeoutSeconds $PdsTimeoutSeconds -Arguments '-project soc.pds -run gen_bit_stream'
    Assert-FpgaStageHistory $implHistory 'post_synthesis'
    foreach ($relative in @('pds/synthesize/soc_top.snr','pds/synthesize/soc_top_syn.vm',
            'pds/synthesize/soc_top_syn.adf')) {
        $path = Join-Path $root $relative
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $synthHashes[$relative]) {
            throw "Post-synthesis route changed audited ADS bytes: $relative"
        }
    }
    $pdsSucceeded = $true
} finally {
    Pop-Location
    if (!$pdsSucceeded) {
        if (Test-Path -LiteralPath $implHistory -PathType Leaf) {
            Copy-Item -LiteralPath $implHistory -Destination (Join-Path $runDir 'pds.failed.impl.tcl') -Force
        }
        if ($hadImplHistory) {
            [IO.File]::WriteAllBytes($implHistory, $savedImplHistory)
        } elseif (Test-Path -LiteralPath $implHistory -PathType Leaf) {
            Remove-Item -LiteralPath $implHistory -Force
        }
    }
}

}
$artifacts = Join-Path $root 'artifacts'
# Both normal and resumed paths use the same original snapshot and saved files.
$buildSnapshot = Read-FpgaActiveSnapshot $root $pdsStartedUtc
$runDir = Join-Path $pds ('input-snapshots/' + $buildSnapshot.run_id)
$preflightPath = Join-Path $runDir 'preflight_gate.json'
if (!(Test-Path -LiteralPath $preflightPath -PathType Leaf)) { throw 'Same-run ADS preflight gate is missing' }
$preflight = [IO.File]::ReadAllText($preflightPath) | ConvertFrom-Json
$snapshotHash = (Get-FileHash -LiteralPath (Join-Path $pds 'build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($preflight.schema -ne 1 -or $preflight.status -cne 'PASS' -or
    $preflight.run_id -cne $buildSnapshot.run_id -or
    $preflight.input_snapshot_sha256 -cne $snapshotHash) {
    throw 'ADS preflight gate does not bind the current input snapshot'
}
Assert-FpgaStageHistory (Join-Path $runDir 'synth.impl.tcl') 'synthesis'
Assert-FpgaStageHistory (Join-Path $pds 'impl.tcl') 'post_synthesis'
if (!(Test-Path -LiteralPath (Join-Path $pds 'soc_pre_synth.pds') -PathType Leaf) -or
    (Get-FileHash -LiteralPath (Join-Path $pds 'soc_pre_synth.pds') -Algorithm SHA256).Hash.ToLowerInvariant() -cne
        $preflight.synth_project_sha256) {
    throw 'Post-synthesis route changed the audited synthesis project'
}
foreach ($relative in @('pds/synthesize/soc_top.snr','pds/synthesize/soc_top_syn.vm',
        'pds/synthesize/soc_top_syn.adf')) {
    $expected = $preflight.synth_hashes.$relative
    if ($expected -notmatch '^[0-9a-f]{64}$' -or
        (Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {
        throw "Post-synthesis project is not bound to the audited ADS bytes: $relative"
    }
}
$bitdir = Join-Path $pds 'generate_bitstream'
$pcf = Join-Path $pds 'device_map\soc_top.pcf'
$prr = Join-Path $pds 'place_route\soc_top_prr.prt'
$synthReport = Join-Path $pds 'synthesize\soc_top.snr'
$synthNetlist = Join-Path $pds 'synthesize\soc_top_syn.vm'
$pnrNetlist = Join-Path $pds 'place_route\soc_top_pnr.netlist'
$timing = Join-Path $pds 'place_route\soc_top_timing_summary_after_hold_fix.txt'
$finalTiming = Join-Path $pds 'report_timing\soc_top.rtr'
$finalTimingXml = Join-Path $pds 'report_timing\rtr.db'
$actualProject = Join-Path $pds 'soc.pds'
$actualHistory = Join-Path $pds 'impl.tcl'
$actualPdsStdout = Join-Path $pds ('input-snapshots/' + $buildSnapshot.run_id + '/pds.stdout.log')
$freshOutputs = @(
    $actualProject, $actualHistory, $actualPdsStdout,
    (Join-Path $pds 'compile\cmr.db'),
    (Join-Path $pds 'compile\formal.pvf'),
    (Join-Path $pds 'compile\include_relation.txt'),
    (Join-Path $pds 'compile\parse_design\screen.pds'),
    (Join-Path $pds 'compile\parse_design\screen.tcl'),
    (Join-Path $pds 'compile\soc_top.cmr'),
    (Join-Path $pds 'compile\soc_top_comp.adf'),
    (Join-Path $pds 'constraint_check\constraint_check.ccr'),
    (Join-Path $pds 'device_map\dmr.db'),
    (Join-Path $pds 'device_map\formal.pvf'),
    (Join-Path $pds 'device_map\soc_top.dmr'),
    (Join-Path $pds 'device_map\soc_top_dmr.prt'),
    $pcf,
    (Join-Path $pds 'device_map\soc_top_map.adf'),
    (Join-Path $pds 'synthesize\snr.db'),
    (Join-Path $pds 'synthesize\formal.pvf'),
    $synthReport,
    (Join-Path $pds 'synthesize\soc_top_controlsets.txt'),
    (Join-Path $pds 'synthesize\soc_top_syn.adf'),
    $synthNetlist,
    (Join-Path $pds 'place_route\prr.db'),
    (Join-Path $pds 'place_route\clock_utilization.txt'),
    (Join-Path $pds 'place_route\soc_top.prr'),
    (Join-Path $pds 'place_route\soc_top_plc.adf'),
    (Join-Path $pds 'place_route\soc_top_pnr.adf'),
    $prr, $pnrNetlist, $timing,
    $finalTimingXml,
    $finalTiming,
    (Join-Path $pds 'report_timing\soc_top_rtp.adf'),
    (Join-Path $pds 'multiseed_summary.csv'),
    (Join-Path $bitdir 'bgr.db'),
    (Join-Path $bitdir 'soc_top.bgr'),
    (Join-Path $bitdir 'soc_top.sbit'),
    (Join-Path $bitdir 'soc_top.bin'),
    (Join-Path $bitdir 'soc_top.smsk')
)
foreach ($output in $freshOutputs) {
    if (!(Test-Path -LiteralPath $output -PathType Leaf)) {
        throw "PDS output missing: $output"
    }
    if ((Get-Item -LiteralPath $output).LastWriteTimeUtc -lt $pdsStartedUtc) {
        throw "Stale PDS output predates this build: $output"
    }
}
$postMapDmr = Join-Path $pds 'device_map/soc_top.dmr'
Assert-FpgaPostMapConstraints $root $postMapDmr
$frozenPostMapDmr = Join-Path $runDir 'post.soc_top.dmr'
Copy-Item -LiteralPath $postMapDmr -Destination $frozenPostMapDmr -Force
if ((Get-FileHash -LiteralPath $frozenPostMapDmr -Algorithm SHA256).Hash -cne
    (Get-FileHash -LiteralPath $postMapDmr -Algorithm SHA256).Hash) {
    throw 'Frozen post-map DMR differs from this run native Device Map report'
}
Assert-FpgaDdrRouteRegistration $root ([IO.File]::ReadAllText($actualProject)) `
    ([IO.File]::ReadAllText((Join-Path $runDir 'pds.parse-post.stdout.log'))) ([IO.File]::ReadAllText($actualPdsStdout)) `
    ([IO.File]::ReadAllText($pnrNetlist))
$cdcPrePath = Join-Path $runDir 'cpu-sys-cdc-ads.json'
$cdcPostPath = Join-Path $runDir 'cpu-sys-cdc-post-route.json'
$cdcPre = [IO.File]::ReadAllText($cdcPrePath) | ConvertFrom-Json
$cdcPost = Invoke-FpgaCdcAdsCheck -Python $PythonPath -Root $root -Vm $synthNetlist -Adf (Join-Path $pds 'synthesize/soc_top_syn.adf') -Ccr (Join-Path $pds 'constraint_check/constraint_check.ccr') -Snapshot (Join-Path $pds 'build_snapshot.json') -Output $cdcPostPath -LogPrefix (Join-Path $runDir 'cpu-sys-cdc-post-route')
if ($cdcPre.vm_sha256 -cne $cdcPost.vm_sha256 -or
    $cdcPre.adf_sha256 -cne $cdcPost.adf_sha256 -or
    $cdcPre.fdc_sha256 -cne $cdcPost.fdc_sha256 -or
    $cdcPre.snapshot_sha256 -cne $cdcPost.snapshot_sha256) {
    throw 'Post-route CDC evidence does not use the audited ADS/FDC/snapshot bytes'
}
$pcfText = [IO.File]::ReadAllText($pcf)
foreach ($marker in @(
    'def_port {sd_clk} LOC=F19 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_cmd} LOC=H14 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_data0} LOC=F18 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_data1} LOC=F20 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_data2} LOC=H17 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_data3} LOC=H15 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {sd_detect_n} LOC=G19 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {audio_bclk} LOC=V26 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {audio_ws} LOC=W26 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {microphone_sd} LOC=U16 VCCIO=3.3 IOSTANDARD=LVCMOS33',
    'def_port {spk_din} LOC=U15 VCCIO=3.3 IOSTANDARD=LVCMOS33')) {
    if (!$pcfText.Contains($marker)) { throw "Mapped MicroSD pin missing: $marker" }
}
$prrText = [IO.File]::ReadAllText($prr)
foreach ($marker in @('|sd_clk|output|YES', '|sd_cmd|inout|YES',
    '|sd_data0|inout|YES', '|sd_data1|inout|YES',
    '|sd_data2|inout|YES', '|sd_data3|inout|YES',
    '|sd_detect_n|input|YES', '|audio_bclk|output|YES',
    '|audio_ws|output|YES', '|microphone_sd|input|YES',
    '|spk_din|output|YES')) {
    if (!$prrText.Contains($marker)) { throw "Placed MicroSD port missing: $marker" }
}
foreach ($netlist in @($synthNetlist, $pnrNetlist)) {
    $netlistText = [IO.File]::ReadAllText($netlist)
    foreach ($port in @('sd_clk', 'sd_cmd', 'sd_data0', 'sd_data1',
            'sd_data2', 'sd_data3', 'sd_detect_n', 'audio_bclk', 'audio_ws',
            'microphone_sd', 'spk_din')) {
        if (!$netlistText.Contains($port)) {
            throw "MicroSD port was removed from netlist: $port in $netlist"
        }
    }
}
$synthNetlistText = [IO.File]::ReadAllText($synthNetlist)
$cpuAdsPath = Join-Path $artifacts 'cpu_ads_controls.json'
$cpuAds = Invoke-CpuAdsCheck $synthNetlist (Join-Path $pds 'build_snapshot.json') $cpuAdsPath `
    (Join-Path $pds ("input-snapshots/" + $buildSnapshot.run_id + '/cpu-ads'))
# Both the normal and FinalizeCompletedBuild exits must consume the original
# pre-PnR ICache proof. A later audit cannot replace an omitted pre-PnR gate.
$icachePrePath = Join-Path $pds ('input-snapshots/' + $buildSnapshot.run_id + '/icache-pad-pre-pnr.json')
if (!(Test-Path -LiteralPath $icachePrePath -PathType Leaf) -or
    (Get-Item -LiteralPath $icachePrePath).LastWriteTimeUtc -lt $pdsStartedUtc) {
    throw 'Fresh same-run pre-PnR ICache ADS result is missing'
}
$icachePreHash = (Get-FileHash -LiteralPath $icachePrePath -Algorithm SHA256).Hash.ToLowerInvariant()
$icacheAds = [IO.File]::ReadAllText($icachePrePath) | ConvertFrom-Json
Assert-IcachePadAdsEvidence $icacheAds $buildSnapshot `
    ((Get-FileHash -LiteralPath (Join-Path $pds 'build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()) `
    ((Get-FileHash -LiteralPath $synthNetlist -Algorithm SHA256).Hash.ToLowerInvariant())
# A source-level handshake is insufficient if ADS removes the hold registers.
foreach ($bit in 0..31) {
    if ($synthNetlistText -notmatch ('GTP_DFF_\w+\s+/\*\s*\\snapshot_frame_count\[' + $bit + '\]')) {
        throw "Snapshot frame register bit $bit was removed by synthesis"
    }
}
foreach ($state in @('snapshot_buffer', 'snapshot_valid', 'hold_seen')) {
    if ($synthNetlistText -notmatch ('GTP_DFF_\w+\s+/\*\s*' + $state + '\s*\*/')) {
        throw "Snapshot hold register was removed by synthesis: $state"
    }
}
foreach ($state in @('sd_dat_oe','cmd_write_latched','hud_toggle','ack_pix',
        'tx0_full','tx1_full','write_buffer_select','write_stop_requested','write_multi_active')) {
    if ($synthNetlistText -notmatch ('GTP_DFF(?:_\w+)?\s+/\*\s*' + $state + '\s*\*/')) {
        throw "SD/HUD register was removed by synthesis: $state"
    }
}
$sdWriteCommandPath = Assert-SdWriteCommandPath $synthNetlistText
foreach ($bit in 0..3) {
    if ($synthNetlistText -notmatch ('GTP_DFF_\w+\s+/\*\s*\\sd_dat_out\[' + $bit + '\]')) {
        throw "SD write DAT lane $bit was removed by synthesis"
    }
}
foreach ($bit in 0..255) {
    if (($bit % 8) -eq 7) { continue } # Font is deliberately7-bit ASCII.
    if ($synthNetlistText -notmatch ('GTP_DFF_\w+\s+/\*\s*\\text_active\[' + $bit + '\]')) {
        throw "HUD text bit $bit was removed by synthesis"
    }
}
foreach ($bit in 0..9) {
    if ($synthNetlistText -notmatch ('GTP_DFF_\w+\s+/\*\s*\\pause_quiet\[' + $bit + '\]')) {
        throw "Snapshot CDC quiet guard bit $bit was removed by synthesis"
    }
}
foreach ($marker in @(
    'module sd_native_mmio',
    'GTP_DFF_SE /* \divider[0]',
    'GTP_DFF_RE /* \cmd_crc[0]',
    'GTP_DFF_RE /* \data_crc0[0]',
    'GTP_DFF_R /* buffer0_ready */',
    'GTP_DFF_R /* buffer1_ready */',
    'GTP_DFF_S /* detect_debounced_n */')) {
    if (!$synthNetlistText.Contains($marker)) {
        throw "Synthesized MicroSD controller logic missing: $marker"
    }
}
# Two independent512-byte banks each require CPU and TX read mirrors. Each
# mirror must map to4096 RAM bits (RAM64X1DP/RAM128X1DP), with matching
# write ports when PDS packs the two views identically.
# DFF fallback and the prior unsupported multi-writer inference are failures.
$flowLog = Join-Path $runDir 'synth.flow.log'
if (!(Test-Path -LiteralPath $flowLog -PathType Leaf) -or
        (Get-Item -LiteralPath $flowLog).LastWriteTimeUtc -lt $pdsStartedUtc) {
    throw 'Fresh PDS synthesis flow log missing'
}
$sdBufferStorage = Assert-SdSectorRamStorage $synthNetlistText `
    ([IO.File]::ReadAllText($flowLog))
foreach ($marker in @('module audio_mmio', 'module i2s_audio_duplex',
        'microphone_count', 'phase_accumulator', 'bit_index')) {
    if (!$synthNetlistText.Contains($marker)) {
        throw "Synthesized audio logic missing: $marker"
    }
}
$synthReportText = [IO.File]::ReadAllText($synthReport)
if ($synthReportText -notmatch '(?m)^Total Latches:\s+0\s*$') {
    throw 'Synthesized design contains latches or lacks a zero-latch report'
}
$finalTimingText = [IO.File]::ReadAllText($finalTiming)
if (!$finalTimingText.Contains('Design Summary : All Constraints Met.')) {
    throw 'Final PDS report_timing constraints are not met'
}
# The PnR summary precedes the DDR-specific hold repair and may be stale.
# Archive the actual final multi-corner summary; keep both report fingerprints.
$summaryStart = $finalTimingText.IndexOf('Design Summary : All Constraints Met.')
$detailStart = [regex]::new('(?m)^Slow Corner\r?$').Match($finalTimingText, $summaryStart)
if (!$detailStart.Success -or $detailStart.Index -le $summaryStart) {
    throw 'Final PDS report lacks a complete timing summary'
}
$timingSummary = $finalTimingText.Substring($summaryStart, $detailStart.Index - $summaryStart).TrimEnd() + "`n"
foreach ($corner in @('Slow','Fast')) {
    foreach ($type in @('Setup','Hold','Recovery','Removal','Minimum Pulse Width')) {
        if (!$timingSummary.Contains("$type Summary($corner Corner):")) {
            throw "Final timing summary is incomplete: $type/$corner"
        }
    }
}
$maxSkew = Assert-FpgaMaxSkewReport $finalTimingXml $finalTiming (Join-Path $pds 'soc.fdc')
$timingScope = Assert-FpgaTimingScope $finalTimingXml (Join-Path $pds 'soc.fdc') (Join-Path $root 'config/timing_scope_baseline.json')
# Recheck immediately before publishing outputs; report inspection can take time.
$buildSnapshot = Read-FpgaActiveSnapshot $root $pdsStartedUtc
if ((Get-FileHash -LiteralPath $icachePrePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $icachePreHash) {
    throw 'Pre-PnR ICache ADS result changed during final checks'
}
$icacheAdsPath = Join-Path $artifacts 'icache_pad_ads.json'
Copy-Item -LiteralPath $icachePrePath -Destination $icacheAdsPath -Force
foreach ($name in @('soc_top.sbit', 'soc_top.bin')) {
    $source = Join-Path $bitdir $name
    if (!(Test-Path -LiteralPath $source)) { throw "PDS output missing: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $artifacts $name) -Force
}
[IO.File]::WriteAllText((Join-Path $artifacts 'timing_summary.txt'), $timingSummary,
    [Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath (Join-Path $pds 'build_snapshot.json') `
    -Destination (Join-Path $artifacts 'build_snapshot.json') -Force

$publishedRaw = [ordered]@{
    'preflight_gate.json' = $preflightPath
    'cpu_sys_cdc_ads_pre.json' = $cdcPrePath
    'cpu_sys_cdc_ads.json' = $cdcPostPath
    'pds_synth_history.txt' = Join-Path $runDir 'synth.impl.tcl'
    'pds_post_history.txt' = $actualHistory
    'pds_synth_project.txt' = Join-Path $runDir 'soc_pre_synth.pds'
    'pds_post_project.txt' = $actualProject
    'pds_synth_parse_stdout.txt' = Join-Path $runDir 'pds.parse-synth.stdout.log'
    'pds_synth_parse_stderr.txt' = Join-Path $runDir 'pds.parse-synth.stderr.log'
    'pds_post_parse_stdout.txt' = Join-Path $runDir 'pds.parse-post.stdout.log'
    'pds_post_parse_stderr.txt' = Join-Path $runDir 'pds.parse-post.stderr.log'
    'pds_synth_stdout.txt' = Join-Path $runDir 'pds.synth.stdout.log'
    'pds_synth_stderr.txt' = Join-Path $runDir 'pds.synth.stderr.log'
    'pds_post_stdout.txt' = $actualPdsStdout
    'pds_post_stderr.txt' = Join-Path $runDir 'pds.stderr.log'
    'pds_synth_constraints.txt' = Join-Path $runDir 'synth.constraint_check.ccr'
    'pds_post_constraints.txt' = Join-Path $pds 'constraint_check/constraint_check.ccr'
    'pds_post_map_constraints.txt' = $postMapDmr
    'pds_synth_flow.txt' = Join-Path $runDir 'synth.flow.log'
    'synth_resource_report.txt' = $synthReport
    'final_timing_report.txt' = $finalTiming
    'final_timing_xml.xml' = $finalTimingXml
}
foreach ($entry in $publishedRaw.GetEnumerator()) {
    if (!(Test-Path -LiteralPath $entry.Value -PathType Leaf)) {
        throw "Native PDS release evidence is missing: $($entry.Value)"
    }
    $target = Join-Path $artifacts $entry.Key
    Copy-Item -LiteralPath $entry.Value -Destination $target -Force
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -cne
        (Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256).Hash) {
        throw "Published PDS evidence copy differs: $($entry.Key)"
    }
}

. (Join-Path $PSScriptRoot 'project_files.ps1')
$inputHashes = ConvertTo-FpgaMap $buildSnapshot.inputs
$outputHashes = Get-FpgaHashMap $root (Get-FpgaOutputPaths)
$reportHashes = [ordered]@{}
$nativeReports = @(
    $synthReport, $synthNetlist, (Join-Path $pds 'synthesize/soc_top_syn.adf'),
    (Join-Path $pds 'constraint_check/constraint_check.ccr'),
    $postMapDmr, $frozenPostMapDmr,
    $pnrNetlist, $timing, $finalTiming, $finalTimingXml, $pcf, $prr,
    $actualProject, $actualHistory, $actualPdsStdout,
    (Join-Path $pds 'soc_pre_synth.pds'),
    (Join-Path $runDir 'soc_pre_synth.pds'),
    (Join-Path $runDir 'soc_post_synth.before_route.pds'),
    (Join-Path $runDir 'synth.impl.tcl'),
    (Join-Path $runDir 'synth.flow.log'),
    (Join-Path $runDir 'synth.constraint_check.ccr'),
    (Join-Path $runDir 'pds.parse-synth.stdout.log'),
    (Join-Path $runDir 'pds.parse-synth.stderr.log'),
    (Join-Path $runDir 'pds.synth.stdout.log'),
    (Join-Path $runDir 'pds.synth.stderr.log'),
    (Join-Path $runDir 'pds.parse-post.stdout.log'),
    (Join-Path $runDir 'pds.parse-post.stderr.log'),
    (Join-Path $runDir 'pds.stderr.log'),
    $preflightPath, $cpuPrePath, $icachePrePath, $cdcPrePath, $cdcPostPath
)
if ((Get-Content -LiteralPath (Join-Path $root 'rtl/cpu/CoreTop.sv') -Raw).Contains('io_shiftSrcPrepared')) {
    $nativeReports += Join-Path $runDir 'prepared-shift-pre-pnr.json'
}
foreach ($path in $nativeReports) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Native PDS report missing: $path" }
    $reportHashes[$path.Substring($root.Length + 1).Replace('\', '/')] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
}
$evidence = [ordered]@{
    schema = 3; run_id = $buildSnapshot.run_id; started_utc = $buildSnapshot.started_utc
    input_snapshot_sha256 = $outputHashes['artifacts/build_snapshot.json']
    release = "V$script:ProjectVersion"; device = 'PG2L100H-6-FBG676'
    pds = '2022.2-SP6.4'; completed_utc = [DateTime]::UtcNow.ToString('o')
    elapsed_seconds = [Math]::Round(([DateTime]::UtcNow - $pdsStartedUtc).TotalSeconds, 1)
    timing = 'All Constraints Met'; timing_summary_source = 'final report_timing'; latches = 0
    max_skew_verified = $true; max_skew_groups = $maxSkew.groups; max_skew_rows = $maxSkew.rows
    timing_scope_verified = $true; timing_scope = $timingScope
    max_skew_rtr_sha256 = $reportHashes['pds/report_timing/soc_top.rtr']
    max_skew_xml_sha256 = $reportHashes['pds/report_timing/rtr.db']
    snapshot_registers_verified = $true; pins_verified = $true
    sd_write_registers_verified = $true; hud_registers_verified = $true
    sd_multiblock_registers_verified = $true
    sd_write_command_path_verified = $true
    sd_write_command_path = $sdWriteCommandPath
    cpu_ads_controls_verified = $true
    icache_pad_ads_verified = $true; icache_pad_ads_sha256 = $icachePreHash
    ordered_post_synthesis_stages_verified = $true
    post_map_constraints_verified = $true
    post_map_dmr_sha256 = $reportHashes['pds/device_map/soc_top.dmr']
    preflight_gate_sha256 = $reportHashes[('pds/input-snapshots/' + $buildSnapshot.run_id + '/preflight_gate.json')]
    synth_adf_sha256 = $preflight.synth_hashes.'pds/synthesize/soc_top_syn.adf'
    synth_vm_sha256 = $preflight.synth_hashes.'pds/synthesize/soc_top_syn.vm'
    synth_snr_sha256 = $preflight.synth_hashes.'pds/synthesize/soc_top.snr'
    cdc_ads_pre_sha256 = $reportHashes[('pds/input-snapshots/' + $buildSnapshot.run_id + '/cpu-sys-cdc-ads.json')]
    cdc_ads_post_sha256 = $reportHashes[('pds/input-snapshots/' + $buildSnapshot.run_id + '/cpu-sys-cdc-post-route.json')]
    ddr_route_registration_verified = $true
    ddr_route_constraint_sha256 = $inputHashes['pds/ddr3_test.rcf']
    ddr_route_target_count = @(Get-FpgaDdrRouteLines).Count
    sd_buffer0_storage = $sdBufferStorage[0]; sd_buffer1_storage = $sdBufferStorage[1]
    report_hashes = $reportHashes; inputs = $inputHashes; outputs = $outputHashes
}
# Never label a new ROM, build recipe or source tree with an older run's hashes.
$null = Read-FpgaActiveSnapshot $root $pdsStartedUtc
Assert-FpgaReleaseEvidence $root ([pscustomobject]$evidence)
[IO.File]::WriteAllText((Join-Path $artifacts 'build_evidence.json'),
    ($evidence | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
$hashItems = @((Get-FpgaOutputPaths | ForEach-Object { Join-Path $root $_ })) +
    @((Join-Path $artifacts 'build_evidence.json'))
$hashes = Get-FileHash -LiteralPath $hashItems -Algorithm SHA256 | ForEach-Object {
    "$($_.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($_.Path))"
}
[IO.File]::WriteAllLines((Join-Path $artifacts 'SHA256SUMS.txt'), $hashes,
    [Text.UTF8Encoding]::new($false))
Write-Output "SoC V$script:ProjectVersion FPGA outputs and build evidence copied to $artifacts"
