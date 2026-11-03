param(
    [string]$PdsShell = '',
    [string]$IcarusBin = '',
    [ValidateSet('Verilator','Icarus')][string]$GateBackend = 'Verilator',
    [string]$MsysRoot = '',
    [string]$WorkDirectory = '',
    [switch]$ReuseSynthesis,
    [ValidateRange(5,600)][int]$SynthesisTimeoutSeconds = 120,
    [ValidateRange(5,600)][int]$BuildTimeoutSeconds = 600,
    [ValidateRange(5,600)][int]$GateTimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (!$PdsShell -and $env:PDS_ROOT) { $PdsShell = Join-Path $env:PDS_ROOT 'bin/pds_shell.exe' }
if (!$PdsShell) {
    $command = Get-Command pds_shell -ErrorAction SilentlyContinue
    if ($command) { $PdsShell = $command.Source }
}
if (!$PdsShell -or !(Test-Path -LiteralPath $PdsShell -PathType Leaf)) {
    throw 'Pass -PdsShell for PDS 2022.2-SP6.4, or set PDS_ROOT.'
}
$PdsShell = [IO.Path]::GetFullPath($PdsShell)
$pdsRoot = Split-Path -Parent (Split-Path -Parent $PdsShell)
$vendor = Join-Path $pdsRoot 'arch/vendor/pango/verilog/simulation'
if ($GateBackend -eq 'Icarus' -and !$IcarusBin) {
    $command = Get-Command iverilog -ErrorAction SilentlyContinue
    if ($command) { $IcarusBin = Split-Path -Parent $command.Source }
}
$required = @((Join-Path $vendor 'GTP_GRS.v'))
if ($GateBackend -eq 'Icarus') {
    if (!$IcarusBin) { throw 'Pass -IcarusBin or add iverilog and vvp to PATH.' }
    $iverilog = Join-Path $IcarusBin 'iverilog.exe'
    $vvp = Join-Path $IcarusBin 'vvp.exe'
    $required += @($iverilog,$vvp)
} else {
    if ($GateTimeoutSeconds -gt 120) { throw 'Verilator simulation is bounded to 120 seconds.' }
    if (!$MsysRoot) { $MsysRoot = $env:MSYS2_ROOT }
    if (!$MsysRoot) { throw 'Pass -MsysRoot <MSYS2 root with MinGW64 Verilator 5.050>, or set MSYS2_ROOT.' }
    $MsysRoot = [IO.Path]::GetFullPath($MsysRoot)
    $bash = Join-Path $MsysRoot 'usr/bin/bash.exe'
    $verilator = Join-Path $MsysRoot 'mingw64/bin/verilator_bin.exe'
    $required += @($bash,$verilator,(Join-Path $MsysRoot 'mingw64/bin/verilator'),(Join-Path $MsysRoot 'mingw64/bin/g++.exe'))
    . (Join-Path $PSScriptRoot 'simulation_tools.ps1')
}
foreach ($file in $required) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing gate-simulation tool/model: $file" }
}
if (!$WorkDirectory) {
    if ($ReuseSynthesis) { throw '-ReuseSynthesis requires an explicit prior -WorkDirectory' }
    $WorkDirectory = Join-Path $projectRoot ('artifacts/selftest/mac-bias-mapping/' + [guid]::NewGuid().ToString('N'))
}
$WorkDirectory = [IO.Path]::GetFullPath($WorkDirectory)
if ((Test-Path -LiteralPath $WorkDirectory) -and !$ReuseSynthesis) {
    throw 'Use a new work directory, or explicitly -ReuseSynthesis to verify matching saved inputs.'
}
if (!$ReuseSynthesis -and @(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'pds_shell.exe'}).Count) {
    throw 'Another PDS process is active; run these two small synthesis jobs serially.'
}
New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
if (!('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs') }
function Get-ProbeHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Write-ProbeText([string]$Path,[string]$Text) {
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
function Invoke-ProbeJob([string]$Program,[string]$Arguments,[string]$Directory,[string]$Name,[int]$Timeout) {
    $stdout = Join-Path $Directory ($Name + '.stdout.txt')
    $stderr = Join-Path $Directory ($Name + '.stderr.txt')
    $code = [CpuSimulation.BoundedProcess]::Run($Program,$Arguments,$Directory,$stdout,$stderr,$Timeout)
    $text = [IO.File]::ReadAllText($stdout) + [IO.File]::ReadAllText($stderr)
    if ($code -ne 0 -or $text -match '(?im)^\s*(?:ERROR:|FATAL:|FAIL\b|%Error)') {
        throw "Probe $Name failed with exit $code; logs: $stdout / $stderr"
    }
}
function Assert-PaddedBiasConnectivity([string]$Netlist) {
    # Match the actual PDS ADS primitive serialization. Unexpected aliases/layout
    # fail for inspection, rather than counting LUTs without proving their use.
    $net = [IO.File]::ReadAllText($Netlist)
    $luts = [regex]::Matches($net,'(?ms)^\s*\(\*\s*PAP_DONT_TOUCH\s*\*\)\s*GTP_LUT6D\b(?<body>.*?\);)')
    if ($luts.Count -ne 768) { throw 'Expected exactly 768 attributed real GTP_LUT6D instances' }
    $bits = [Collections.Generic.HashSet[int]]::new()
    $pairs = [Collections.Generic.HashSet[int]]::new()
    foreach ($lut in $luts) {
        $body = $lut.Groups['body'].Value
        $instance = [regex]::Match($body,'(?m)^\s*\\write_data_pad\[(\d+)\]\.u_hold_dual_lut\s+\(')
        if (!$instance.Success) { throw 'Unexpected pad instance name' }
        $pair = [int]$instance.Groups[1].Value
        if ($pair -lt 0 -or $pair -ge 768 -or !$pairs.Add($pair)) { throw 'Repeated/out-of-range pad pair' }
        $low = 2*$pair
        $high = $low+1
        if (!$bits.Add($low) -or !$bits.Add($high)) { throw 'Repeated pad bit' }
        $init = [regex]::Match($body,'\.INIT\s*\(([^)]*)\)').Groups[1].Value -replace '\s',''
        if ($init -cne ("64'b"+('1100'*8)+('1010'*8))) { throw "Non-identity dual LUT INIT at pair $pair" }
        $ports = [ordered]@{
            I0="io_wdata[$low]"; I1="io_wdata[$high]"
            I2="1'b0"; I3="1'b0"; I4="1'b0"; I5="1'b1"
            Z5="memory_MPORT_data[$low]"; Z="memory_MPORT_data[$high]"
        }
        foreach ($port in $ports.Keys) {
            $matches = [regex]::Matches($body,'\.'+$port+'\s*\(([^)]*)\)')
            if ($matches.Count -ne 1 -or ($matches[0].Groups[1].Value -replace '\s','') -cne $ports[$port]) {
                throw "Incorrect $port connection at pad pair $pair"
            }
        }
    }
    $rams = [regex]::Matches($net,'(?ms)\bGTP_RAM32X2DP\b(?<body>.*?\);)')
    if ($rams.Count -ne 768) { throw 'Expected exactly 768 two-bit distributed RAMs' }
    $lanes = [Collections.Generic.HashSet[int]]::new()
    foreach ($ram in $rams) {
        $body = $ram.Groups['body'].Value
        $instance = [regex]::Match($body,'(?m)^\s*memory_(\d+)\s+\(')
        if (!$instance.Success) { throw 'Unexpected RAM lane instance name' }
        $lane = [int]$instance.Groups[1].Value
        if ($lane -lt 0 -or $lane -ge 768 -or !$lanes.Add($lane)) { throw 'Repeated/out-of-range RAM lane' }
        $expected = '{memory_MPORT_data['+(2*$lane+1)+'],memory_MPORT_data['+(2*$lane)+']}'
        $connections = [regex]::Matches($body,'\.DI\s*\(([^)]*)\)')
        if ($connections.Count -ne 1 -or ($connections[0].Groups[1].Value -replace '\s','') -cne $expected) {
            throw "RAM lane $lane bypasses or swaps its write-data pads"
        }
    }
    if ($net -match '(?m)^\s*assign\s+memory_MPORT_data') { throw 'Unexpected bypass driver on the pad output bus' }
    # Each output must have exactly its LUT driver and its corresponding RAM load.
    $clean = [regex]::Replace($net,'(?s)/\*.*?\*/|(?m)//[^\r\n]*','')
    $counts = New-Object 'int[]' 1536
    foreach ($reference in [regex]::Matches($clean,'memory_MPORT_data\[(\d+)\]')) {
        $bit = [int]$reference.Groups[1].Value
        if ($bit -lt 0 -or $bit -ge 1536) { throw 'Pad output index outside reviewed width' }
        $counts[$bit]++
    }
    if (@($counts | Where-Object {$_ -ne 2}).Count) { throw 'Pad output has missing/extra driver or load' }
    $withoutBits = [regex]::Replace($clean,'memory_MPORT_data\[\d+\]','PAD_BIT')
    $withoutDecl = [regex]::Replace($withoutBits,'(?m)^\s*wire\s+\[1535:0\]\s+memory_MPORT_data\s*;','')
    if ($withoutDecl -match '\bmemory_MPORT_data\b') { throw 'Unexpected whole-bus alias/driver/usage' }
    return [ordered]@{bits_checked=$bits.Count;pad_pairs_checked=$pairs.Count;ram_lanes_checked=$lanes.Count;primitive='GTP_LUT6D';init='CCCCCCCC_AAAAAAAA';i2="1'b0";i3="1'b0";i4="1'b0";i5="1'b1";unique_driver_and_load_bits=1536;bypass=$false}
}
$sourcePath = Join-Path $projectRoot 'rtl/mac_accel/MacAccelCore.v'
$sourceHash = Get-ProbeHash $sourcePath
$source = [IO.File]::ReadAllText($sourcePath).Replace("`r`n","`n")
$bank = [regex]::Match($source,'(?ms)^module Bank1R1W_2\(.*?^endmodule')
if (!$bank.Success) { throw 'MAC bias bank module was not found' }
$attribute = ' /* synthesis syn_ramstyle="lut_ram" */'
if ([regex]::Matches($bank.Value,[regex]::Escape($attribute)).Count -ne 1) {
    throw 'The production bias bank must have exactly one reviewed lut_ram attribute'
}
# The historical DRM experiment and reference contain no pad or synthesis branch.
# Strip only this exact reviewed production block; unexpected edits fail closed.
$padBlock = @'
`ifdef SYNTHESIS
  // Preserve two independent identity paths in one dual-output LUT for hold repair.
  genvar pad_pair;
  generate
    for (pad_pair = 0; pad_pair < 768; pad_pair = pad_pair + 1) begin : write_data_pad
      (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_hold_dual_lut (
        .I0(io_wdata[2*pad_pair]), .I1(io_wdata[2*pad_pair+1]),
        .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
        .Z5(memory_MPORT_data[2*pad_pair]), .Z(memory_MPORT_data[2*pad_pair+1])
      );
    end
  endgenerate
`else
  assign memory_MPORT_data = io_wdata;
`endif
'@
if ([regex]::Matches($bank.Value,[regex]::Escape($padBlock)).Count -ne 1) {
    throw 'Expected exactly one reviewed 1536-bit physical identity-pad block'
}
$noPadBank = $bank.Value.Replace($padBlock,'  assign memory_MPORT_data = io_wdata;')
if ($noPadBank -cmatch 'SYNTHESIS|GTP_LUT6D|write_data_pad') { throw 'Reference still contains a pad branch' }
$baseline = $noPadBank.Replace($attribute,'').Replace('module Bank1R1W_2(','module bias_bank(')
$needle = 'reg [1535:0] memory [0:15];'
if ([regex]::Matches($baseline,[regex]::Escape($needle)).Count -ne 1) { throw 'Unexpected bias RAM width/depth' }
$candidate = $bank.Value.Replace('module Bank1R1W_2(','module bias_bank(')
$tcl = "add_design `"bias_bank.v`"`nadd_constraint `"clock.fdc`"`nset_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676`ncompile -top_module bias_bank -system_verilog`nsynthesize -ads -selected_syn_tool_opt 2 -disable_io_insertion`n"
$fdc = "create_clock -name {clock} [get_ports {io_clk}] -period {20.202}`n"
Write-Host "MAC_BIAS_PROBE owner=$PID; backend=$GateBackend; each synthesis <=$SynthesisTimeoutSeconds s, model build <=$BuildTimeoutSeconds s, gate simulation <=$GateTimeoutSeconds s. Stop process $PID to close its current child job."
$reports = [ordered]@{}
$connectivity = $null
$hashes = [ordered]@{}
foreach ($mode in @('baseline_drm','padded_lut_ram')) {
    $directory = Join-Path $WorkDirectory $mode
    $text = if ($mode -eq 'baseline_drm') { $baseline } else { $candidate }
    $inputs = [ordered]@{ 'bias_bank.v'=$text+"`n"; 'run.tcl'=$tcl; 'clock.fdc'=$fdc }
    if ($ReuseSynthesis) {
        foreach ($name in $inputs.Keys) {
            $path = Join-Path $directory $name
            if (!(Test-Path -LiteralPath $path -PathType Leaf) -or [IO.File]::ReadAllText($path) -cne $inputs[$name]) {
                throw "Saved probe input is stale or different: $mode/$name"
            }
        }
    } else {
        New-Item -ItemType Directory -Path $directory | Out-Null
        foreach ($name in $inputs.Keys) { Write-ProbeText (Join-Path $directory $name) $inputs[$name] }
        Invoke-ProbeJob $PdsShell '-file run.tcl' $directory 'pds' $SynthesisTimeoutSeconds
    }
    $reportPath = Join-Path $directory 'synthesize/bias_bank.snr'
    $netlistPath = Join-Path $directory 'synthesize/bias_bank_syn.vm'
    foreach ($path in @($reportPath,$netlistPath)) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing probe output: $path" }
        if ((Get-Item -LiteralPath $path).LastWriteTimeUtc -lt (Get-Item -LiteralPath (Join-Path $directory 'bias_bank.v')).LastWriteTimeUtc) {
            throw "Probe output predates its source: $path"
        }
    }
    $report = [IO.File]::ReadAllText($reportPath)
    if ($report -notmatch 'version 2022\.2-SP6\.4' -or $report -notmatch '(?m)^Total Latches:\s+0\s*$') {
        throw 'Unexpected PDS version or inferred latch in probe'
    }
    $drm = [double]::Parse([regex]::Match($report,'Total DRM = ([0-9.]+)').Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)
    $lut = [int][regex]::Match($report,'Total LUTs: (\d+)').Groups[1].Value
    $ff = [int][regex]::Match($report,'Total Registers: (\d+)').Groups[1].Value
    if (($mode -eq 'baseline_drm' -and ($drm -ne 22 -or $lut -ne 6 -or $ff -ne 0)) -or
        ($mode -eq 'padded_lut_ram' -and ($drm -ne 0 -or $lut -ne 1542 -or $ff -ne 1536 -or
            $report -notmatch '(?m)^GTP_RAM32X2DP\s+768 uses' -or
            $report -notmatch '(?m)^GTP_LUT6D\s+768 uses'))) {
        throw "Unexpected RAM mapping in $mode; inspect the real report"
    }
    if ($mode -eq 'padded_lut_ram') { $connectivity = Assert-PaddedBiasConnectivity $netlistPath }
    $reports[$mode] = [ordered]@{drm36k_equivalent=$drm;luts=$lut;registers=$ff;latches=0}
    foreach ($name in @('bias_bank.v','clock.fdc','run.tcl','synthesize/bias_bank.snr','synthesize/bias_bank_syn.vm')) {
        $hashes["$mode/$name"] = Get-ProbeHash (Join-Path $directory $name)
    }
}
Write-ProbeText (Join-Path $WorkDirectory 'bias_bank_reference.v') ($baseline.Replace('module bias_bank(','module bias_bank_reference(')+"`n")
Copy-Item -LiteralPath (Join-Path $projectRoot 'sim/tb_mac_bias_mapping.v') -Destination (Join-Path $WorkDirectory 'tb_bias_mapping.v') -Force
# Bind the complete vendor model dependency closure before either simulator runs.
# Comments are excluded so prose mentioning other primitives is not a dependency.
$models = [ordered]@{}
$pending = [Collections.Generic.Queue[string]]::new()
$pending.Enqueue('GTP_GRS')
$netlist = Join-Path $WorkDirectory 'padded_lut_ram/synthesize/bias_bank_syn.vm'
$modelText = [regex]::Replace([IO.File]::ReadAllText($netlist),'(?s)/\*.*?\*/|(?m)//[^\r\n]*','')
foreach ($match in [regex]::Matches($modelText,'\b(?:GTP|INT)_\w+\b')) { $pending.Enqueue($match.Value) }
while ($pending.Count) {
    $name = $pending.Dequeue()
    if ($models.Contains($name+'.v')) { continue }
    $path = Join-Path $vendor ($name+'.v')
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing vendor dependency: $name" }
    $models[$name+'.v'] = Get-ProbeHash $path
    $modelText = [regex]::Replace([IO.File]::ReadAllText($path),'(?s)/\*.*?\*/|(?m)//[^\r\n]*','')
    foreach ($match in [regex]::Matches($modelText,'\b(?:GTP|INT)_\w+\b')) { $pending.Enqueue($match.Value) }
}
foreach ($name in @('bias_bank_reference.v','tb_bias_mapping.v')) {
    $hashes[$name] = Get-ProbeHash (Join-Path $WorkDirectory $name)
}
$tools = [ordered]@{}
foreach ($file in $required + @($PSCommandPath,(Join-Path $PSScriptRoot 'bounded_process.cs'),(Join-Path $PSScriptRoot 'simulation_tools.ps1'))) {
    $tools[$file] = Get-ProbeHash $file
}
$commands = [ordered]@{}
$simulation = [ordered]@{ backend=$GateBackend;build_exit=0;simulation_exit=0 }
if ($GateBackend -eq 'Icarus') {
    $arguments = '-g2012 -s tb_bias_mapping -y "' + $vendor + '" -o "bias_mapping.vvp" "tb_bias_mapping.v" "bias_bank_reference.v" "padded_lut_ram/synthesize/bias_bank_syn.vm"'
    $commands.build = $iverilog+' '+$arguments
    $commands.simulation = $vvp+' bias_mapping.vvp'
    Invoke-ProbeJob $iverilog $arguments $WorkDirectory 'iverilog' 60
    Invoke-ProbeJob $vvp 'bias_mapping.vvp' $WorkDirectory 'gate' $GateTimeoutSeconds
    $simulation.state_scope = 'four_state'
    $simulation.model_sha256 = Get-ProbeHash (Join-Path $WorkDirectory 'bias_mapping.vvp')
    $outputNames = @('iverilog.stdout.txt','iverilog.stderr.txt')
} else {
    # Same options as the actual full-width fallback. No blackboxes, assertion
    # disabling, RTL defines, changed vendor models or reduced test workload.
    $modelDir = Join-Path $WorkDirectory 'verilator_model'
    $options = @('--binary','--timing','--language','1800-2012','--top-module','tb_bias_mapping',
        '--output-groups','0','-j','1','-Wno-fatal','-Wno-TIMESCALEMOD','-Wno-WIDTHEXPAND','-Wno-WIDTHTRUNC',
        '--Mdir',(ConvertTo-MsysPath $modelDir),'-y',(ConvertTo-MsysPath $vendor))
    $options += @('tb_bias_mapping.v','bias_bank_reference.v','padded_lut_ram/synthesize/bias_bank_syn.vm' | ForEach-Object {
        ConvertTo-MsysPath (Join-Path $WorkDirectory $_)
    })
    $commands.build = 'verilator '+(($options | ForEach-Object { Quote-BashArgument $_ }) -join ' ')
    $buildScript = Join-Path $WorkDirectory 'build_verilator.sh'
    Write-ProbeText $buildScript ("#!/usr/bin/env bash`nset -euo pipefail`nexport PATH=/mingw64/bin:/usr/bin:`$PATH`n"+
        'cd '+(Quote-BashArgument (ConvertTo-MsysPath $WorkDirectory))+"`n"+$commands.build+"`n")
    $executable = Join-Path $modelDir 'Vtb_bias_mapping.exe'
    $commands.simulation = $executable
    $savedPath = $env:PATH
    try {
        $env:PATH=(Join-Path $MsysRoot 'mingw64/bin')+';'+$savedPath
        Invoke-ProbeJob $verilator '--version' $WorkDirectory 'verilator_version' 5
        $simulation.version = [IO.File]::ReadAllText((Join-Path $WorkDirectory 'verilator_version.stdout.txt')).Trim()
        if ($simulation.version -notmatch '^Verilator 5\.050\b') { throw 'This vendor-model gate requires the verified Verilator 5.050 toolchain.' }
        Invoke-ProbeJob $bash ('--noprofile --norc "'+(ConvertTo-MsysPath $buildScript)+'"') $WorkDirectory 'verilator_build' $BuildTimeoutSeconds
        if (!(Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Missing newly built Verilator model' }
        Invoke-ProbeJob $executable '' $WorkDirectory 'gate' $GateTimeoutSeconds
    } finally { $env:PATH=$savedPath }
    $simulation.state_scope = 'initialized_known_inputs_two_state'
    $simulation.limitations = 'Not X/Z or uninitialized-state four-state equivalence; no SDF timing proof. Original 512-cycle TB initializes all 16 entries before comparison.'
    $simulation.model_sha256 = Get-ProbeHash $executable
    $simulation.host_build_jobs = 1
    $simulation.build_timeout_seconds = $BuildTimeoutSeconds
    $simulation.assertion_disabling_options = @()
    $simulation.blackbox_options = @()
    $simulation.rtl_defines = @()
    $simulation.parameter_overrides = @()
    $outputNames = @('build_verilator.sh','verilator_build.stdout.txt','verilator_build.stderr.txt','verilator_version.stdout.txt','verilator_version.stderr.txt')
}
$simulation.simulation_timeout_seconds = $GateTimeoutSeconds
$gateText = [IO.File]::ReadAllText((Join-Path $WorkDirectory 'gate.stdout.txt'))
if (!$gateText.Contains('BIAS_MAPPING_GATE_PASS cycles=512 bits=1536 reset_hold_read_first_write_bounds')) {
    throw 'Gate test did not reach the exact success marker'
}
if ((Get-ProbeHash $sourcePath) -cne $sourceHash) { throw 'MAC RTL changed while the mapping check ran' }
foreach ($name in $hashes.Keys) {
    if ((Get-ProbeHash (Join-Path $WorkDirectory $name)) -cne $hashes[$name]) { throw "Gate input changed: $name" }
}
foreach ($name in $models.Keys) {
    if ((Get-ProbeHash (Join-Path $vendor $name)) -cne $models[$name]) { throw "Vendor model changed: $name" }
}
foreach ($name in $tools.Keys) {
    if ((Get-ProbeHash $name) -cne $tools[$name]) { throw "Test tool/helper changed: $name" }
}
foreach ($name in $outputNames + @('gate.stdout.txt','gate.stderr.txt')) {
    $hashes[$name] = Get-ProbeHash (Join-Path $WorkDirectory $name)
}
$result = [ordered]@{
    schema=3;status='PASS';scope='Historical unpadded DRM mapping and current padded LUTRAM ADS functional check within simulation_state_scope; not full SoC placement, routed timing or board acceptance'
    synthesis_reused=[bool]$ReuseSynthesis;source_rtl_sha256=$sourceHash;runner_sha256=(Get-ProbeHash $PSCommandPath)
    source_sha256=$sourceHash;test_script_sha256=(Get-ProbeHash $PSCommandPath)
    simulation_backend=$GateBackend;simulation_state_scope=$simulation.state_scope;build_exit=0;simulation_exit=0
    simulation=$simulation;commands=$commands;tool_and_helper_files=$tools;inputs_unchanged=$true
    bank_width=1536;bank_depth=16;gate_cycles=512;mapping=$reports;pad_connectivity=$connectivity;files=$hashes;vendor_models=$models
    pds_sha256=(Get-ProbeHash $PdsShell)
    reproduce='powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_mac_bias_mapping.ps1 -PdsShell <pds_shell.exe> -MsysRoot <MSYS2 root with MinGW64 Verilator 5.050>; use -GateBackend Icarus -IcarusBin <bin> for the explicit four-state alternative'
}
Write-ProbeText (Join-Path $WorkDirectory 'result.json') (($result | ConvertTo-Json -Depth 7)+"`n")
Write-Output "MAC_BIAS_MAPPING_PASS result=$WorkDirectory/result.json"
