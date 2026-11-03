# Synthetic data factory for evidence-contract tests only. Never runs ADS and
# never writes into the real project's artifacts directory.
function New-TestIcachePadEvidence($Snapshot, [string]$SnapshotHash, [string]$NetlistHash) {
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    $hashes = [ordered]@{ 'pds/build_snapshot.json' = $SnapshotHash; 'pds/synthesize/soc_top_syn.vm' = $NetlistHash }
    foreach ($path in @('rtl/cpu/CoreTop.sv', 'rtl/cpu/source.json',
        'rtl/cpu/emit-config.json', 'scripts/audit_icache_pad_ads.py')) { $hashes[$path] = $inputs[$path] }
    return [ordered]@{
        schema = 1; status = 'PASS'; scope = 'INTEGRATED_ADS_ONLY'; run_id = $Snapshot.run_id
        input_snapshot_sha256 = $SnapshotHash; netlist_sha256 = $NetlistHash
        source_rtl_sha256 = $inputs['rtl/cpu/CoreTop.sv']; source_json_sha256 = $inputs['rtl/cpu/source.json']
        emit_config_sha256 = $inputs['rtl/cpu/emit-config.json']; checker_sha256 = $inputs['scripts/audit_icache_pad_ads.py']
        input_hashes = $hashes; inputs_unchanged = $true
        hierarchy = 'soc_top/u_cpu/u_cpu_wrapper/u_cpu/core/frontend/cache'
        post_pnr_physical_retention_proven = $false; routed_hold_margin_proven = $false
        connectivity = [ordered]@{
            primitive = 'GTP_LUT6D'; pairs = 64; bits = 128; init = 'CCCCCCCC_AAAAAAAA'
            preservation_attribute = 'PAP_DONT_TOUCH'; upstream_ff_bits = 128
            unique_driver_and_two_way_loads = $true; bypass = $false
            pad_module_sha256 = 'a' * 64; icache_module_sha256 = 'b' * 64
            ways = @(
                @{ instance = 'wayMem_0_ext'; module = 'wayMem_128x256'; mapping = '256_GTP_RAM128X1SP'; write_bits_checked = 256; padded_low_bits = 128; module_sha256 = 'd' * 64 }
                @{ instance = 'wayMem_1_ext'; module = 'wayMem_128x256_unq4'; mapping = '4_GTP_DRM36K_E1'; write_bits_checked = 256; padded_low_bits = 128; module_sha256 = 'e' * 64 }
            )
        }
    }
}

function Test-IcachePrePnrGate([string]$Fixture, [string]$PythonPath, [string]$ScriptsRoot) {
    # The exact production prefix through ICache and snapshot code run in a child Windows Job. Only the two
    # Python auditors are test doubles. No FPGA tool or hardware can be invoked.
    foreach ($name in @('build_cpu_ads_gate.ps1','build_snapshot.ps1','bounded_process.cs','clock_policy.ps1','timing_scope.ps1')) {
        Copy-Item -LiteralPath (Join-Path $ScriptsRoot $name) -Destination (Join-Path $Fixture "scripts/$name")
    }
    # Scope this fixture to the exact production prefix ending at ICache.
    # Later RF/vision/SD preflight stages have independent actual-native gates.
    # No test-only bypass or switch is added to the production helper.
    $helperSource=[IO.File]::ReadAllText((Join-Path $ScriptsRoot 'build_cpu_ads_gate.ps1'))
    $endMarker='Write-Output "ICACHE_PRE_PNR_ADS_PASS run=$($snapshot.run_id) pairs=64 bits=128 ways=2 scope=ADS_ONLY"'
    $at=$helperSource.IndexOf($endMarker,[StringComparison]::Ordinal)
    if($at -lt 0 -or $helperSource.LastIndexOf($endMarker,[StringComparison]::Ordinal) -ne $at){throw 'Unknown production ICache stage boundary'}
    $prefix=$helperSource.Substring(0,$at+$endMarker.Length)+[Environment]::NewLine
    [IO.File]::WriteAllText((Join-Path $Fixture 'scripts/build_cpu_ads_gate.ps1'),$prefix,[Text.UTF8Encoding]::new($false))
    New-Item -ItemType Directory -Path (Join-Path $Fixture 'rtl/soc') -Force|Out-Null
    [IO.File]::WriteAllText((Join-Path $Fixture 'rtl/soc/soc_top.v'),'// SYNTHETIC fixture, no optional engines enabled. Never synthesize.
module soc_top; endmodule',[Text.UTF8Encoding]::new($false))
    foreach ($relative in (Get-FpgaStagedAssets).Keys) {
        $dest = Join-Path $Fixture $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $Fixture (Get-FpgaStagedAssets)[$relative]) -Destination $dest -Force
    }
    $cpuDouble = @'
import hashlib, json, pathlib, sys
args = sys.argv
snap_path = pathlib.Path(args[args.index('--input-snapshot') + 1])
snap = json.loads(snap_path.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
# Carry the complete synthetic CPU/PMA/UART contract from the enclosing
# snapshot fixture, then bind it to this helper run. Never weaken real gates.
result = json.loads((snap_path.parent.parent / 'artifacts/cpu_ads_controls.json').read_text(encoding='utf-8-sig'))
result.update(schema_version=1,status='PASS',frontend_cases=85760,return_cases=10240,pma_address_cases=2144,rsmem_hint_cases=17152,
input_snapshot_run_id=snap['run_id'],input_snapshot_sha256=sha(snap_path),audit_script_sha256=sha(__file__),netlist_sha256=sha(args[1]))
if 'scripts/audit_uart_tx_pad_ads.py' in snap['inputs']:
    result['uart_tx_pad_contract'].update(run_id=snap['run_id'],input_snapshot_sha256=sha(snap_path),vm_sha256=sha(args[1]),
        checker_sha256=snap['inputs']['scripts/audit_uart_tx_pad_ads.py'],parser_sha256=snap['inputs']['scripts/audit_icache_pad_ads.py'],
        uart_rtl_sha256=snap['inputs']['rtl/soc/uart_tx_fifo.v'])
pathlib.Path(args[args.index('--output') + 1]).write_text(json.dumps(result))
'@
    [IO.File]::WriteAllText((Join-Path $Fixture 'scripts/audit_cpu_ads.py'), $cpuDouble)
    $icacheDouble = @'
import json, pathlib, sys, time
args = sys.argv
root = pathlib.Path(args[args.index('--project-root') + 1])
mode = (root / 'test-mode.txt').read_text()
if mode == 'exit7': sys.exit(7)
if mode == 'timeout': time.sleep(90)
result = {'status':'PASS'} if mode == 'incomplete' else json.loads((root / 'test-result.json').read_text(encoding='utf-8-sig'))
pathlib.Path(args[args.index('--output') + 1]).write_text(json.dumps(result))
'@
    [IO.File]::WriteAllText((Join-Path $Fixture 'scripts/audit_icache_pad_ads.py'), $icacheDouble)
    if (-not ('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $ScriptsRoot 'bounded_process.cs') }
    $checks = @()
    foreach ($mode in @('matching','exit7','incomplete','timeout')) {
        $snap = New-FpgaSnapshot $Fixture
        $netlist = Join-Path $Fixture 'pds/synthesize/soc_top_syn.vm'
        New-Item -ItemType Directory -Path (Split-Path -Parent $netlist) -Force | Out-Null
        [IO.File]::WriteAllText($netlist, '// SYNTHETIC ONLY; never interpreted by an FPGA tool')
        $snapshotHash = (Get-FileHash -LiteralPath (Join-Path $Fixture 'pds/build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        $netlistHash = (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant()
        $proof = New-TestIcachePadEvidence $snap $snapshotHash $netlistHash
        [IO.File]::WriteAllText((Join-Path $Fixture 'test-result.json'), ($proof | ConvertTo-Json -Depth 8))
        [IO.File]::WriteAllText((Join-Path $Fixture 'test-mode.txt'), $mode)
        $stdout = Join-Path $Fixture "$mode.stdout.txt"
        $stderr = Join-Path $Fixture "$mode.stderr.txt"
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Fixture 'scripts/build_cpu_ads_gate.ps1') +
            '" -PythonPath "' + $PythonPath + '" -ProjectRoot "' + $Fixture + '"'
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $exit = [CpuSimulation.BoundedProcess]::Run((Get-Process -Id $PID).Path, $arguments, $Fixture, $stdout, $stderr, 80)
        $out = [IO.File]::ReadAllText($stdout); $err = [IO.File]::ReadAllText($stderr)
        if (!$out.Contains('CPU_PRE_PNR_ADS_PASS')) { throw "Helper fixture failed before tested ICache stage: $err" }
        if ($mode -eq 'matching') {
            if ($exit -ne 0 -or !$out.Contains('ICACHE_PRE_PNR_ADS_PASS')) { throw "Helper positive rejected: $err" }
        } else {
            $marker = switch ($mode) { 'exit7' { 'audit failed exit=7' }; 'incomplete' { 'ICache ADS evidence' }; 'timeout' { 'exceeded 60 seconds' } }
            if ($exit -eq 0 -or !$err.Contains($marker)) { throw "Helper $mode did not propagate the expected failure: $err" }
        }
        $checks += [ordered]@{ name = "actual_helper_$mode"; status = 'PASS'; scope = 'SYNTHETIC_AUDITORS_NO_PDS'
            exit_code = $exit; seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 2)
            stdout = $out.Trim(); stderr = $err.Trim() }
    }
    return $checks
}
