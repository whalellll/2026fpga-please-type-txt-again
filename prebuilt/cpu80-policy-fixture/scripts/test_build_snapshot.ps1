param([string]$ReportPath = '', [string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'test_icache_pad_fixture.ps1')
. (Join-Path $PSScriptRoot 'test_uart_tx_pad_fixture.ps1')
. (Join-Path $PSScriptRoot 'test_fpga_stage_fixture.ps1')
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$fixture = Join-Path $tempBase ('fpga_snapshot_fixture_' + [guid]::NewGuid().ToString('N'))
$checks = New-Object 'Collections.Generic.List[string]'
function Write-Fixture([string]$Relative, [string]$Text) {
    $path = Get-FpgaSafePath $fixture $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, $Text, [Text.UTF8Encoding]::new($false))
}
function Assert-Rejected([string]$Name, [scriptblock]$Action, [string]$Message) {
    $rejected = $false
    try { & $Action } catch {
        if ($_.Exception.Message -notlike $Message) { throw "Unexpected failure in ${Name}: $($_.Exception.Message)" }
        $rejected = $true
    }
    if (!$rejected) { throw "Fixture was incorrectly accepted: $Name" }
    $checks.Add($Name)
}
function Test-Mutation([string]$Name, [string]$Relative, [scriptblock]$Action, [string]$Message) {
    $path = Get-FpgaSafePath $fixture $Relative
    $original = [IO.File]::ReadAllBytes($path)
    $oldTime = [IO.File]::GetLastWriteTimeUtc($path)
    try {
        [IO.File]::AppendAllText($path, "`nchanged", [Text.UTF8Encoding]::new($false))
        # Hash validation must reject edits even when an mtime check would pass.
        [IO.File]::SetLastWriteTimeUtc($path, $oldTime)
        Assert-Rejected $Name $Action $Message
    } finally { [IO.File]::WriteAllBytes($path, $original) }
}
function Set-TestMaxSkewSlack([string]$XmlText, [string]$Slack) {
    [xml]$doc = $XmlText
    $nodes = @($doc.SelectNodes('/tables/table[@id="report_timing_slow_path_max_skew"]/row[1]/data[2]'))
    if ($nodes.Count -ne 1 -or $nodes[0].InnerText -ceq $Slack) {
        throw 'Max Skew mutation did not select one different native slack value'
    }
    $nodes[0].InnerText = $Slack
    return $doc.OuterXml
}
try {
    New-Item -ItemType Directory -Path $fixture | Out-Null
    foreach ($directory in @('config','rtl','sw','ip','scripts','artifacts','pds')) {
        New-Item -ItemType Directory -Path (Join-Path $fixture $directory) | Out-Null
    }
    Write-Fixture 'VERSION' '6.1'
    Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'config/timing_scope_baseline.json') `
        -Destination (Join-Path $fixture 'config/timing_scope_baseline.json')
    Write-Fixture 'config/clocks.json' '{"schema":1,"input_hz":27000000,"pll_vco_hz":891000000,"cpu_divisor":18,"cpu_hz":49500000,"sys_hz":49500000,"timebase_hz":49500000,"integer_hz_rounding":"nearest_half_up"}'
    Write-Fixture 'rtl/CoreTop.sv' 'fixture RTL; no synthesis is performed'
    Write-Fixture 'rtl/cpu/CoreTop.sv' 'fixture CPU RTL; no synthesis is performed'
    Write-Fixture 'rtl/cpu/emit-config.json' '{"fixture":true}'
    Write-Fixture 'rtl/cpu/source.json' '{"fixture":true}'
    Write-Fixture 'sw/main.c' 'fixture C'
    Write-Fixture 'ip/fixture.idf' 'fixture IP'
    foreach ($name in @('soc.tcl','soc_post_synth.tcl','soc_gui.pds','soc.fdc',
            'audit_cpu_sys_cdc_ads.py')) {
        Write-Fixture "pds/$name" 'fixture project'
    }
    Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'pds/soc.fdc') `
        -Destination (Join-Path $fixture 'pds/soc.fdc') -Force
    Write-Fixture 'pds/ddr3_test.rcf' ((Get-FpgaDdrRouteLines) -join "`n")
    $routeProject = '(_widget wgt_edit_route_cons (_attribute _click_to_run (_switch ON)) (_input (_file "ddr3_test.rcf" (_format rcf) (_timespec "2026-09-26T14:04:46"))))'
    $routeHistory = 'Executing : add_constraint soc.fdc successfully.' + [Environment]::NewLine +
        'Executing : add_constraint ddr3_test.rcf successfully.'
    $routeStdout = ''
    $expectedRouteNets = @(
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [0]'
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [1]'
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[1].ddrphy_data_slice/adj_wrdqs [0]'
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [61]'
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [10]'
        'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/adj_wrdata_mask [7]'
        'u_cpu/u_cpu_wrapper/u_cpu/core/frontend/ftqAlloc [3]'
    )
    $expectedRouteLines = @($expectedRouteNets | ForEach-Object { 'def_route -prior_net {' + $_ + '}' })
    $routeStdout += "`n" + (($expectedRouteLines | ForEach-Object { 'Executing : ' + $_ + ' successfully.' }) -join "`n")
    if (((Get-FpgaDdrRouteLines) -join "`n") -cne ($expectedRouteLines -join "`n")) {
        throw 'Route contract differs from the seven independently specified net names'
    }
    $routeNets = ($expectedRouteNets | ForEach-Object { $_ + ';' }) -join "`n"
    $routeCheck = { Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory $routeStdout $routeNets }
    & $routeCheck
    $checks.Add('ddr_route_registration_fixture_accepted')
    Test-Mutation 'changed_rcf_rejected' 'pds/ddr3_test.rcf' $routeCheck '*exactly the seven*'
    $routeInputPath = Get-FpgaSafePath $fixture 'pds/ddr3_test.rcf'
    $originalRouteInput = [IO.File]::ReadAllBytes($routeInputPath)
    try {
        Write-Fixture 'pds/ddr3_test.rcf' ($expectedRouteLines[0..1] -join "`n")
        Assert-Rejected 'rcf_old_two_vendor_nets_only_rejected' $routeCheck '*exactly the seven*'
        Write-Fixture 'pds/ddr3_test.rcf' (($expectedRouteLines + $expectedRouteLines[2]) -join "`n")
        Assert-Rejected 'rcf_duplicate_priority_rejected' $routeCheck '*exactly the seven*'
    } finally { [IO.File]::WriteAllBytes($routeInputPath, $originalRouteInput) }
    for ($routeIndex = 0; $routeIndex -lt $expectedRouteNets.Count; $routeIndex++) {
        $net = $expectedRouteNets[$routeIndex]
        $successLine = 'Executing : ' + $expectedRouteLines[$routeIndex] + ' successfully.'
        Assert-Rejected "rcf_target_${routeIndex}_missing_execution_rejected" {
            Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory ($routeStdout.Replace($successLine, '')) $routeNets
        } '*no unique successful PDS priority execution*'
        Assert-Rejected "rcf_target_${routeIndex}_failed_execution_rejected" {
            Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory ($routeStdout.Replace($successLine, $successLine.Replace(' successfully.', ' failed.'))) $routeNets
        } '*no unique successful PDS priority execution*'
        Assert-Rejected "rcf_target_${routeIndex}_missing_rejected" {
            Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory $routeStdout ($routeNets.Replace($net + ';', ''))
        } '*absent from the actual PnR netlist*'
        Assert-Rejected "rcf_target_${routeIndex}_wrong_spacing_rejected" {
            Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory $routeStdout ($routeNets.Replace($net, $net.Replace(' [', '[')))
        } '*absent from the actual PnR netlist*'
        try {
            Write-Fixture 'pds/ddr3_test.rcf' (($expectedRouteLines | Where-Object { $_ -cne $expectedRouteLines[$routeIndex] }) -join "`n")
            Assert-Rejected "rcf_priority_${routeIndex}_missing_rejected" $routeCheck '*exactly the seven*'
        } finally { [IO.File]::WriteAllBytes($routeInputPath, $originalRouteInput) }
    }
    Assert-Rejected 'rcf_duplicate_success_execution_rejected' {
        Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory ($routeStdout + "`nExecuting : " + $expectedRouteLines[2] + ' successfully.') $routeNets
    } '*no unique successful PDS priority execution*'
    Assert-Rejected 'rcf_wrong_widget_rejected' {
        Assert-FpgaDdrRouteInput $fixture ($routeProject.Replace('wgt_edit_route_cons', 'wgt_other'))
    } '*native PDS route input*'
    Assert-Rejected 'rcf_missing_native_timespec_rejected' {
        Assert-FpgaDdrRouteInput $fixture ($routeProject.Replace(' (_timespec "2026-09-26T14:04:46")', ''))
    } '*native PDS route input*'
    Assert-Rejected 'rcf_missing_execution_rejected' {
        Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory '' $routeNets
    } '*no unique successful PDS priority execution*'
    Assert-Rejected 'rcf_missing_history_rejected' {
        Assert-FpgaDdrRouteRegistration $fixture $routeProject 'Executing : add_constraint soc.fdc successfully.' $routeStdout $routeNets
    } '*native PDS parse record*'
    Assert-Rejected 'rcf_wrong_net_spacing_rejected' {
        Assert-FpgaDdrRouteRegistration $fixture $routeProject $routeHistory $routeStdout ($routeNets.Replace('gate [', 'gate['))
    } '*absent from the actual PnR netlist*'
    Write-Fixture 'scripts/build_fpga.ps1' '# fixture build recipe'
    Write-Fixture 'scripts/audit_cpu_ads.py' '# fixture audit recipe'
    Write-Fixture 'scripts/audit_frontend_metadata_ads.py' '# fixture frontend metadata audit'
    Write-Fixture 'scripts/ads_bdd.py' '# fixture BDD implementation'
    Write-Fixture 'scripts/audit_icache_pad_ads.py' '# fixture ICache audit recipe'
    Write-Fixture 'scripts/audit_uart_tx_pad_ads.py' '# fixture UART hold-pad audit recipe'
    Write-Fixture 'rtl/soc/uart_tx_fifo.v' '// fixture UART source'
    Write-Fixture 'scripts/riscv_toolchain.ps1' @'
$CpuMarch = 'rv32ima_zicsr_zifencei'
$CpuAbi = 'ilp32'
$CpuGccVersion = '14.2.0'
$CpuTarget = 'riscv32-unknown-elf'
'@
    Write-Fixture 'artifacts/SONG.PCM' 'fixture media'
    foreach ($name in Get-FpgaFirmwareNames) {
        [IO.File]::WriteAllBytes((Join-Path $fixture "artifacts/$name.bin"), [byte[]]@(1,2,3,4))
        [IO.File]::WriteAllBytes((Join-Path $fixture "artifacts/$name.elf"), [byte[]]@(127,69,76,70,1,2,3,4))
        $metadata = [ordered]@{
            binary = "$name.bin"
            binary_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture "artifacts/$name.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
            compiler_target = 'riscv32-unknown-elf'; compiler_version = '14.2.0'
            march = 'rv32ima_zicsr_zifencei'; abi = 'ilp32'; optimization = '-O2'
            compiler_sha256 = 'a' * 64
            elf_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture "artifacts/$name.elf") -Algorithm SHA256).Hash.ToLowerInvariant()
            elf_metadata = @{ ElfClass = 'ELF32'; Flags = '0x0 (fixture)' }
            code_validation = @{ Result = 'RV32IMA mnemonic/width whitelist fixture'; BytesChecked = 4; ExplicitIllegalInstructionFixture = $false }
        }
        Write-Fixture "artifacts/$name.build.json" ($metadata | ConvertTo-Json -Depth 4)
    }
    Write-Fixture 'artifacts/bootrom.hex' ("04030201`n" + ("00000000`n" * 32767))
    $assets = Get-FpgaStagedAssets
    foreach ($relative in $assets.Keys) {
        if (!(Test-Path -LiteralPath (Join-Path $fixture $assets[$relative]))) { Write-Fixture $assets[$relative] 'fixture ROM' }
        Write-Fixture $relative ([IO.File]::ReadAllText((Join-Path $fixture $assets[$relative])))
    }
    $snapshot = New-FpgaSnapshot $fixture
    $started = [datetime]::Parse($snapshot.started_utc)
    $jsonSnapshot = Read-FpgaActiveSnapshot $fixture $started
    $checks.Add('unchanged_original_snapshot_accepted')
    # Normal and Finalize both consume this JSON reader before writing evidence.
    if ($jsonSnapshot.inputs.GetType().FullName -cne 'System.Management.Automation.PSCustomObject') {
        throw 'Fixture must exercise Read-FpgaActiveSnapshot JSON object inputs'
    }
    $checks.Add('json_snapshot_reader_returns_pscustomobject')
    # Execute only the real build entry's map assignment and evidence fields;
    # never invoke its software builders, PDS flow, or artifact publication.
    $parseTokens = $null; $parseErrors = $null
    $buildAst = [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot 'build_fpga.ps1'), [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors) { throw 'Cannot parse the build entry for JSON evidence regression' }
    $mapAssignment = @($buildAst.FindAll({ param($node)
        $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -ceq '$inputHashes'
    }, $true))
    $evidenceAssignment = @($buildAst.FindAll({ param($node)
        $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -ceq '$evidence'
    }, $true))
    if ($mapAssignment.Count -ne 1 -or $evidenceAssignment.Count -ne 1) { throw 'Build evidence assignment must be unique' }
    $tables = @($evidenceAssignment[0].Right.FindAll({ param($node)
        $node -is [Management.Automation.Language.HashtableAst]
    }, $true))
    if ($tables.Count -ne 1) { throw 'Build evidence must expose one field table' }
    $fields = @($tables[0].KeyValuePairs | Where-Object {
        $_.Item1.Value -in @('ddr_route_constraint_sha256', 'ddr_route_target_count', 'inputs')
    } | ForEach-Object { $_.Item1.Extent.Text + ' = ' + $_.Item2.Extent.Text })
    if ($fields.Count -ne 3) { throw 'Build evidence lacks the RCF fields or full input map' }
    $makeEvidence = [scriptblock]::Create('param($buildSnapshot)' + "`n" +
        $mapAssignment[0].Extent.Text + "`n[pscustomobject]@{`n" + ($fields -join "`n") + "`n}")
    $jsonEvidence = & $makeEvidence $jsonSnapshot
    $expectedRcfHash = (Get-FileHash -LiteralPath $routeInputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($jsonEvidence.ddr_route_constraint_sha256 -cne $expectedRcfHash -or $jsonEvidence.ddr_route_target_count -ne 7) {
        throw 'JSON-read build evidence lost the exact six-net RCF SHA256 or target count'
    }
    Assert-FpgaMap $snapshot.inputs $jsonEvidence.inputs 'JSON-read build evidence input coverage'
    $checks.Add('normal_and_finalize_json_inputs_preserve_six_net_rcf_evidence')
    $normal = { Assert-FpgaSnapshot $fixture $snapshot -CheckStaged }
    $finalize = { $null = Read-FpgaActiveSnapshot $fixture $started }
    $recipeInputs = Get-FpgaHashMap $fixture (Get-FpgaRecipeInputPaths $fixture -AllowHdmiRegeneration)
    $recipeCheck = { Assert-FpgaMap $recipeInputs (Get-FpgaHashMap $fixture (Get-FpgaRecipeInputPaths $fixture -AllowHdmiRegeneration)) 'Firmware build inputs' }
    Test-Mutation 'source_change_during_software_build_rejected' 'sw/main.c' $recipeCheck '*Firmware build inputs mismatch*'
    $defaultRecipeInputs = Get-FpgaHashMap $fixture (Get-FpgaRecipeInputPaths $fixture)
    Test-Mutation 'default_build_rejects_hdmi_asset_change' 'rtl/video/header_bitmap.hex' {
        Assert-FpgaMap $defaultRecipeInputs (Get-FpgaHashMap $fixture (Get-FpgaRecipeInputPaths $fixture)) 'Default recipe inputs'
    } '*Default recipe inputs mismatch*'
    $headerPath = Join-Path $fixture 'rtl/video/header_bitmap.hex'
    $originalHeader = [IO.File]::ReadAllBytes($headerPath)
    try {
        [IO.File]::AppendAllText($headerPath, ' regenerated output')
        & $recipeCheck
        $checks.Add('intentional_hdmi_regeneration_allowed_before_freeze')
    } finally { [IO.File]::WriteAllBytes($headerPath, $originalHeader) }
    Test-Mutation 'normal_rejects_changed_rcf_with_old_mtime' 'pds/ddr3_test.rcf' $normal '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'normal_rejects_changed_rtl_with_old_mtime'  'rtl/CoreTop.sv' $normal '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'finalize_rejects_changed_c_source' 'sw/main.c' $finalize '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'finalize_rejects_changed_build_recipe' 'scripts/build_fpga.ps1' $finalize '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'normal_rejects_changed_metadata_audit' 'scripts/audit_frontend_metadata_ads.py' $normal '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'normal_rejects_changed_bdd_engine' 'scripts/ads_bdd.py' $normal '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'normal_rejects_changed_canonical_rom' 'artifacts/bootrom.hex' $normal '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'finalize_rejects_changed_staged_rom' 'pds/bootrom.hex' $finalize '*Actual staged ROMs mismatch*'
    Test-Mutation 'finalize_rejects_changed_binary' 'artifacts/bootloader.bin' $finalize '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'finalize_rejects_changed_elf' 'artifacts/bootloader.elf' $finalize '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'normal_rejects_changed_firmware_metadata' 'artifacts/mac_selftest.build.json' $normal '*Frozen FPGA inputs mismatch*'
    Write-Fixture 'rtl/added.sv' 'new source'
    Assert-Rejected 'added_input_rejected' $normal '*inventory changed*'
    Remove-Item -LiteralPath (Join-Path $fixture 'rtl/added.sv')
    Assert-Rejected 'old_start_timestamp_rejected' { $null = Read-FpgaActiveSnapshot $fixture ($started.AddMinutes(-1)) } '*start UTC does not match*'
    Test-Mutation 'saved_original_copy_tampering_rejected' ("pds/input-snapshots/" + $snapshot.run_id + '/files/rtl/CoreTop.sv') $finalize '*Saved original FPGA inputs mismatch*'
    $old = $snapshot | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $old.schema = 0
    Assert-Rejected 'obsolete_snapshot_schema_rejected' { Assert-FpgaSnapshot $fixture $old } '*obsolete*'
    $old.schema = 1; $old.release = 'V5.4'
    Assert-Rejected 'old_v5_4_snapshot_rejected' { Assert-FpgaSnapshot $fixture $old } '*foreign*'
    Copy-Item -LiteralPath (Join-Path $fixture 'pds/build_snapshot.json') -Destination (Join-Path $fixture 'artifacts/build_snapshot.json')
    foreach ($relative in $assets.Keys) { Remove-Item -LiteralPath (Get-FpgaSafePath $fixture $relative) }
    foreach ($relative in @('artifacts/soc_top.sbit','artifacts/soc_top.bin','artifacts/timing_summary.txt')) {
        Write-Fixture $relative 'SYNTHETIC FIXTURE ONLY - not FPGA or board evidence'
    }
    foreach ($name in @('preflight_gate.json','cpu_sys_cdc_ads_pre.json','cpu_sys_cdc_ads.json',
            'pds_synth_history.txt','pds_post_history.txt',
            'pds_synth_project.txt','pds_post_project.txt',
            'pds_synth_parse_stdout.txt','pds_synth_parse_stderr.txt',
            'pds_post_parse_stdout.txt','pds_post_parse_stderr.txt',
            'pds_synth_stdout.txt','pds_synth_stderr.txt',
            'pds_post_stdout.txt','pds_post_stderr.txt',
            'pds_synth_constraints.txt','pds_post_constraints.txt','pds_post_map_constraints.txt','pds_synth_flow.txt',
            'synth_resource_report.txt','final_timing_report.txt','final_timing_xml.xml')) {
        Write-Fixture "artifacts/$name" 'SYNTHETIC PDS STAGE EVIDENCE ONLY'
    }
    Write-Fixture 'artifacts/pds_synth_history.txt' "set_arch fixture`ncompile`nsynthesize`n"
    Write-Fixture 'artifacts/pds_post_history.txt' "dev_map fixture`npnr`nreport_timing -report_max_skew`nreport_power`ngen_netlist`ngen_bit_stream`n"
    $skewReports = New-TestFpgaMaxSkewReports (Join-Path $fixture 'pds/soc.fdc')
    Write-Fixture 'artifacts/final_timing_xml.xml' $skewReports.xml
    Write-Fixture 'artifacts/final_timing_report.txt' $skewReports.rtr
    foreach ($stageName in @('synth','post')) {
        Write-Fixture "artifacts/pds_${stageName}_parse_stdout.txt" "Executing : add_constraint soc.fdc successfully.`nExecuting : add_constraint ddr3_test.rcf successfully.`n"
    }
    $snapshotHash = (Get-FileHash -LiteralPath (Join-Path $fixture 'artifacts/build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $cpuAds = [ordered]@{
        schema_version = 1; status = 'PASS'; scope = 'SYNTHETIC FIXTURE ONLY - not ADS or board evidence'
        frontend_cases = 85760; return_cases = 10240; pma_address_cases = 2144; rsmem_hint_cases = 17152
        input_snapshot_sha256 = $snapshotHash; input_snapshot_run_id = $snapshot.run_id
        cpu_rtl_sha256 = $snapshot.inputs['rtl/cpu/CoreTop.sv']
        cpu_emit_config_sha256 = $snapshot.inputs['rtl/cpu/emit-config.json']
        production_rom_sha256 = $snapshot.inputs['artifacts/bootrom.hex']
        audit_script_sha256 = $snapshot.inputs['scripts/audit_cpu_ads.py']
        netlist_sha256 = 'c' * 64
        pma_contract = [ordered]@{
            address_cases = 2144; consumer_cases = 4288
            consumers = @('Lsu.N13', 'Lsu.N965')
            mapped_outputs = [ordered]@{ _N1=@{}; _N2=@{}; _N3=@{}; _N4=@{} }
            consumer_pma_inputs = [ordered]@{ N13=@('_N2','_N3','_N4'); N965=@('_N1') }
            output_values = [ordered]@{ _N1=@(0,1); _N2=@(0,1); _N3=@(0,1); _N4=@(0,1) }
        }
    }
    $cpuAds.uart_tx_pad_contract = New-TestUartTxPadEvidence $snapshot $snapshotHash ('c' * 64)
    Write-Fixture 'artifacts/cpu_ads_controls.json' ($cpuAds | ConvertTo-Json -Depth 8)
    $fusedPma = $cpuAds | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    $sharedPma = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/attributes/N7'
    $fusedPma.pma_contract = [pscustomobject]@{
        address_cases = 2144; consumer_cases = 68608; control_combinations = 16
        variant = 'fused_single_output'; consumers = @('Lsu.N13', 'Lsu.N965')
        mapped_outputs = [pscustomobject]@{ N7 = [pscustomobject]@{} }
        consumer_pma_inputs = [pscustomobject]@{ N13=@($sharedPma); N965=@($sharedPma) }
        output_values = [pscustomobject]@{ N7=@(0,1) }
    }
    Assert-FpgaCpuPmaContract $fusedPma
    $fusedPma.pma_contract.control_combinations = 1
    Assert-Rejected 'cpu_ads_fused_control_coverage_rejected' {
        Assert-FpgaCpuPmaContract $fusedPma
    } '*fused PMA contract*'
    $icacheAds = New-TestIcachePadEvidence $snapshot $snapshotHash ('c' * 64)
    Write-Fixture 'artifacts/icache_pad_ads.json' ($icacheAds | ConvertTo-Json -Depth 8)
    $icacheHash = (Get-FileHash -LiteralPath (Join-Path $fixture 'artifacts/icache_pad_ads.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $stage = New-TestFpgaStageEvidence $fixture $snapshot $snapshotHash
    $evidence = [pscustomobject]@{
        schema = 3; run_id = $snapshot.run_id; started_utc = $snapshot.started_utc
        completed_utc = $started.AddSeconds(1).ToString('o')
        input_snapshot_sha256 = $snapshotHash; cpu_ads_controls_verified = $true
        icache_pad_ads_verified = $true; icache_pad_ads_sha256 = $icacheHash
        ordered_post_synthesis_stages_verified = $true
        preflight_gate_sha256 = $stage.preflight_sha256
        synth_adf_sha256 = $stage.synth_hashes['pds/synthesize/soc_top_syn.adf']
        synth_vm_sha256 = $stage.synth_hashes['pds/synthesize/soc_top_syn.vm']
        synth_snr_sha256 = $stage.synth_hashes['pds/synthesize/soc_top.snr']
        cdc_ads_pre_sha256 = $stage.reports[('pds/input-snapshots/' + $snapshot.run_id + '/cpu-sys-cdc-ads.json')]
        cdc_ads_post_sha256 = $stage.cdc_sha256
        post_map_constraints_verified = $true
        post_map_dmr_sha256 = $stage.reports['pds/device_map/soc_top.dmr']
        max_skew_verified = $true; max_skew_groups = 10; max_skew_rows = 20
        max_skew_rtr_sha256 = $stage.reports['pds/report_timing/soc_top.rtr']
        max_skew_xml_sha256 = $stage.reports['pds/report_timing/rtr.db']
        report_hashes = $stage.reports
        inputs = $snapshot.inputs; outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
    }
    $evidence | Add-Member ddr_route_registration_verified $true
    $evidence | Add-Member ddr_route_constraint_sha256 $snapshot.inputs['pds/ddr3_test.rcf']
    $evidence | Add-Member ddr_route_target_count $expectedRouteNets.Count
    Assert-FpgaReleaseEvidence $fixture $evidence
    $skewXmlPath = Join-Path $fixture 'artifacts/final_timing_xml.xml'
    $skewRtrPath = Join-Path $fixture 'artifacts/final_timing_report.txt'
    $skewFdcPath = Join-Path $fixture 'pds/soc.fdc'
    $skewXmlBytes = [IO.File]::ReadAllBytes($skewXmlPath)
    $skewRtrBytes = [IO.File]::ReadAllBytes($skewRtrPath)
    $skewXmlText = [IO.File]::ReadAllText($skewXmlPath)
    $skewRtrText = [IO.File]::ReadAllText($skewRtrPath)
    try {
        Write-Fixture 'artifacts/final_timing_xml.xml' '<tables></tables>'
        Assert-Rejected 'max_skew_missing_xml_table_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*lacks one slow Max Skew table*'
        Write-Fixture 'artifacts/final_timing_xml.xml' ($skewXmlText.Replace('id="report_timing_fast_path_max_skew"', 'id="wrong_fast_table"'))
        Assert-Rejected 'max_skew_missing_fast_xml_table_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*lacks one fast Max Skew table*'
        [xml]$skewDoc = $skewXmlText
        $fastTable = $skewDoc.SelectSingleNode('/tables/table[@id="report_timing_fast_path_max_skew"]')
        $null = $fastTable.RemoveChild($fastTable.SelectSingleNode('./row'))
        Write-Fixture 'artifacts/final_timing_xml.xml' $skewDoc.OuterXml
        Assert-Rejected 'max_skew_missing_gray_group_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*does not have ten Gray groups*'
        Write-Fixture 'artifacts/final_timing_xml.xml' (Set-TestMaxSkewSlack $skewXmlText '-0.001')
        Assert-Rejected 'max_skew_negative_slack_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*Max Skew violation*'
        Write-Fixture 'artifacts/final_timing_xml.xml' (Set-TestMaxSkewSlack $skewXmlText 'N/A')
        Assert-Rejected 'max_skew_missing_numeric_slack_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*nonnumeric timing value*'
        Write-Fixture 'artifacts/final_timing_xml.xml' ([regex]::Replace($skewXmlText, 'Line Num [0-9]+', 'Line Num 99999', 1))
        Assert-Rejected 'max_skew_unknown_fdc_line_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*unknown or duplicate FDC line*'
        Write-Fixture 'artifacts/final_timing_xml.xml' ($skewXmlText.Replace('u_ar_fifo/wr_gray_rd1[0]', 'u_ar_fifo/wr_gray_rd2[0]'))
        Assert-Rejected 'max_skew_wrong_stage1_endpoint_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*misses the reviewed Gray launch/stage1 pair*'
        [xml]$skewDoc = $skewXmlText
        $firstBranch = $skewDoc.SelectSingleNode('/tables/table[@id="report_timing_slow_path_max_skew"]/row[1]/row[1]')
        $null = $firstBranch.RemoveChild($firstBranch.SelectSingleNode('./row'))
        Write-Fixture 'artifacts/final_timing_xml.xml' $skewDoc.OuterXml
        Assert-Rejected 'max_skew_missing_gray_bit_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*does not cover five Gray bits*'
        Write-Fixture 'artifacts/final_timing_xml.xml' $skewXmlText
        Write-Fixture 'artifacts/final_timing_report.txt' ($skewRtrText.Replace('Flow Command: report_timing -report_max_skew', 'Flow Command: report_timing'))
        Assert-Rejected 'max_skew_missing_rtr_command_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*lacks the Max Skew command*'
        Write-Fixture 'artifacts/final_timing_report.txt' ($skewRtrText.Replace('pds/report_timing/rtr.db', 'missing.xml'))
        Assert-Rejected 'max_skew_missing_rtr_xml_output_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*lacks the Max Skew command*'
        Write-Fixture 'artifacts/final_timing_report.txt' ($skewRtrText.Replace('All Constraints Met.', 'Constraints Violated.'))
        Assert-Rejected 'max_skew_rtr_violation_rejected' {
            Assert-FpgaMaxSkewReport $skewXmlPath $skewRtrPath $skewFdcPath
        } '*lacks the Max Skew command*'
    } finally {
        [IO.File]::WriteAllBytes($skewXmlPath, $skewXmlBytes)
        [IO.File]::WriteAllBytes($skewRtrPath, $skewRtrBytes)
    }
    $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $bad.max_skew_xml_sha256 = '0' * 64
    Assert-Rejected 'max_skew_foreign_report_hash_rejected' {
        Assert-FpgaReleaseEvidence $fixture $bad
    } '*Max Skew release evidence*'
    try {
        Write-Fixture 'artifacts/final_timing_xml.xml' (Set-TestMaxSkewSlack $skewXmlText '-0.001')
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.max_skew_xml_sha256 = $bad.outputs['artifacts/final_timing_xml.xml']
        $bad.report_hashes.'pds/report_timing/rtr.db' = $bad.max_skew_xml_sha256
        Assert-Rejected 'max_skew_rehashed_negative_xml_rejected' {
            Assert-FpgaReleaseEvidence $fixture $bad
        } '*Max Skew violation*'
    } finally { [IO.File]::WriteAllBytes($skewXmlPath, $skewXmlBytes) }
    $postHistoryPath = Join-Path $fixture 'artifacts/pds_post_history.txt'
    $postHistoryBytes = [IO.File]::ReadAllBytes($postHistoryPath)
    try {
        Write-Fixture 'artifacts/pds_post_history.txt' ([IO.File]::ReadAllText($postHistoryPath).Replace('report_timing -report_max_skew', 'report_timing'))
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.report_hashes.'pds/impl.tcl' = $bad.outputs['artifacts/pds_post_history.txt']
        Assert-Rejected 'max_skew_native_option_missing_rejected' {
            Assert-FpgaReleaseEvidence $fixture $bad
        } '*lacks report_timing -report_max_skew*'
    } finally { [IO.File]::WriteAllBytes($postHistoryPath, $postHistoryBytes) }
    Assert-FpgaReleaseEvidence $fixture $evidence
    $validCdc = [IO.File]::ReadAllText((Join-Path $fixture 'artifacts/cpu_sys_cdc_ads.json')) | ConvertFrom-Json
    $badCdc = $validCdc | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $badCdc.payloads[0].mapped_ram_x2dp = 18
    Assert-Rejected 'payload_primitive_mix_rejected' {
        Assert-FpgaCdcEvidenceRecords $badCdc 'fixture'
    } '*mapped payload RAM evidence*'
    $badCdc = $validCdc | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $badCdc.payloads[0].launch_clock = $badCdc.payloads[0].capture_clock
    Assert-Rejected 'payload_wrong_launch_clock_rejected' {
        Assert-FpgaCdcEvidenceRecords $badCdc 'fixture'
    } '*mapped payload RAM evidence*'
    $badCdc = $validCdc | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $badCdc.first_stage_crossings[0].source_clock = 'sys_clk'
    Assert-Rejected 'sync_wrong_source_clock_rejected' {
        Assert-FpgaCdcEvidenceRecords $badCdc 'fixture'
    } '*mapped first-stage evidence*'
    $badCdc = $validCdc | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $badCdc.first_stage_crossings[0].fdc_matches.max_delay.capture_ff_objects = 2
    Assert-Rejected 'sync_wrong_logical_selector_rejected' {
        Assert-FpgaCdcEvidenceRecords $badCdc 'fixture'
    } '*first-stage FDC selector*'
    $dmrPath = Join-Path $fixture 'artifacts/pds_post_map_constraints.txt'
    $dmrBytes = [IO.File]::ReadAllBytes($dmrPath)
    foreach ($target in @(
            @{ name='gray'; pattern='^set_max_delay\b.*u_axi_cdc/u_ar_fifo/wr_gray' },
            @{ name='payload'; pattern='^set_max_delay\b.*u_axi_cdc/u_ar_fifo/storage' },
            @{ name='first_stage'; pattern='^set_max_delay\b.*u_irq_sync/timer_c1' }
        )) {
        try {
            $dmrText = [IO.File]::ReadAllText($dmrPath)
            $oneDirective = @($dmrText -split '\r?\n' | Where-Object { $_ -match $target.pattern })[0]
            if (!$oneDirective) { throw "Fixture DMR lacks $($target.name) target" }
            Write-Fixture 'artifacts/pds_post_map_constraints.txt' ($dmrText.Replace($oneDirective + "`n", ''))
            $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
            $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
            $bad.post_map_dmr_sha256 = $bad.outputs['artifacts/pds_post_map_constraints.txt']
            $bad.report_hashes.'pds/device_map/soc_top.dmr' = $bad.post_map_dmr_sha256
            $bad.report_hashes.(('pds/input-snapshots/' + $snapshot.run_id + '/post.soc_top.dmr')) = $bad.post_map_dmr_sha256
            Assert-Rejected "post_map_missing_$($target.name)_directive_rejected" {
                Assert-FpgaReleaseEvidence $fixture $bad
            } '*Native post-map DMR lacks one exact FDC directive*'
        } finally { [IO.File]::WriteAllBytes($dmrPath, $dmrBytes) }
    }
    $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $bad.synth_adf_sha256 = '0' * 64
    Assert-Rejected 'foreign_post_synthesis_adf_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*Post-synthesis ADS adf fingerprint*'
    $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $bad.report_hashes.(('pds/input-snapshots/' + $snapshot.run_id + '/synth.constraint_check.ccr')) = '0' * 64
    Assert-Rejected 'foreign_preflight_ccr_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*Post-synthesis preflight proof*'
    $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $bad.ordered_post_synthesis_stages_verified = $false
    Assert-Rejected 'missing_ordered_stage_gate_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*Post-synthesis stage evidence*'
    $cdcPath = Join-Path $fixture 'artifacts/cpu_sys_cdc_ads.json'
    $cdcBytes = [IO.File]::ReadAllBytes($cdcPath)
    try {
        $foreignCdc = [IO.File]::ReadAllText($cdcPath) | ConvertFrom-Json
        $foreignCdc.ccr_sha256 = '0' * 64
        Write-Fixture 'artifacts/cpu_sys_cdc_ads.json' ($foreignCdc | ConvertTo-Json -Depth 10)
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.cdc_ads_post_sha256 = $bad.outputs['artifacts/cpu_sys_cdc_ads.json']
        $bad.report_hashes.(('pds/input-snapshots/' + $snapshot.run_id + '/cpu-sys-cdc-post-route.json')) = $bad.cdc_ads_post_sha256
        Assert-Rejected 'foreign_post_route_ccr_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*CPU/SYS CDC post-route ADS/CCR evidence*'
    } finally { [IO.File]::WriteAllBytes($cdcPath, $cdcBytes) }
    $postHistoryPath = Join-Path $fixture 'artifacts/pds_post_history.txt'
    $postHistoryBytes = [IO.File]::ReadAllBytes($postHistoryPath)
    try {
        [IO.File]::AppendAllText($postHistoryPath, "compile`n")
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.report_hashes.'pds/impl.tcl' = $bad.outputs['artifacts/pds_post_history.txt']
        Assert-Rejected 'post_stage_resynthesis_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*post_synthesis native history has wrong compile count*'
    } finally { [IO.File]::WriteAllBytes($postHistoryPath, $postHistoryBytes) }
    $postParserPath = Join-Path $fixture 'artifacts/pds_post_parse_stdout.txt'
    $postParserBytes = [IO.File]::ReadAllBytes($postParserPath)
    try {
        Write-Fixture 'artifacts/pds_post_parse_stdout.txt' 'Executing : add_constraint soc.fdc successfully.'
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.report_hashes.(('pds/input-snapshots/' + $snapshot.run_id + '/pds.parse-post.stdout.log')) =
            $bad.outputs['artifacts/pds_post_parse_stdout.txt']
        Assert-Rejected 'post_stage_missing_rcf_registration_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*post parser did not register ddr3_test.rcf*'
    } finally { [IO.File]::WriteAllBytes($postParserPath, $postParserBytes) }
    foreach ($entry in @(
        @('missing_icache_flag', { $bad.icache_pad_ads_verified = $null }),
        @('wrong_icache_artifact_hash', { $bad.icache_pad_ads_sha256 = '0' * 64 })
    )) {
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        & $entry[1]
        Assert-Rejected $entry[0] { Assert-FpgaReleaseEvidence $fixture $bad } '*ICache ADS evidence*'
    }
    foreach ($entry in @(
        @('icache_foreign_run', { $badIcache.run_id = '0' * 32 }),
        @('icache_foreign_snapshot', { $badIcache.input_snapshot_sha256 = '0' * 64 }),
        @('icache_foreign_netlist', { $badIcache.netlist_sha256 = '0' * 64 }),
        @('icache_foreign_source', { $badIcache.source_rtl_sha256 = '0' * 64 }),
        @('icache_foreign_provenance', { $badIcache.source_json_sha256 = '0' * 64 }),
        @('icache_foreign_config', { $badIcache.emit_config_sha256 = '0' * 64 }),
        @('icache_foreign_checker', { $badIcache.checker_sha256 = '0' * 64 }),
        @('icache_omitted_input', { $badIcache.input_hashes.PSObject.Properties.Remove('rtl/cpu/source.json') }),
        @('icache_wrong_input_map', { $badIcache.input_hashes.'rtl/cpu/CoreTop.sv' = '0' * 64 }),
        @('icache_missing_scope', { $badIcache.scope = $null }),
        @('icache_false_physical_claim', { $badIcache.post_pnr_physical_retention_proven = $true }),
        @('icache_false_timing_claim', { $badIcache.routed_hold_margin_proven = $true }),
        @('icache_missing_boundary', { $badIcache.PSObject.Properties.Remove('routed_hold_margin_proven') }),
        @('icache_wrong_boolean_type', { $badIcache.inputs_unchanged = 'true' }),
        @('icache_wrong_hierarchy', { $badIcache.hierarchy = 'Icache' }),
        @('icache_pair_missing', { $badIcache.connectivity.pairs = 63 }),
        @('icache_wrong_init', { $badIcache.connectivity.init = '00000000_00000000' }),
        @('icache_ff_missing', { $badIcache.connectivity.upstream_ff_bits = 127 }),
        @('icache_bypass', { $badIcache.connectivity.bypass = $true }),
        @('icache_way_missing', { $badIcache.connectivity.ways = @($badIcache.connectivity.ways[0]) }),
        @('icache_unknown_mapping', { $badIcache.connectivity.ways[0].mapping = 'UNKNOWN' }),
        @('icache_wrong_way_instance', { $badIcache.connectivity.ways[1].instance = 'wayMem_0_ext' }),
        @('icache_missing_di', { $badIcache.connectivity.ways[0].write_bits_checked = 255 })
    )) {
        $badIcache = $icacheAds | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        & $entry[1]
        Write-Fixture 'artifacts/icache_pad_ads.json' ($badIcache | ConvertTo-Json -Depth 10)
        $bad = $evidence | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        $bad.icache_pad_ads_sha256 = $bad.outputs['artifacts/icache_pad_ads.json']
        Assert-Rejected $entry[0] { Assert-FpgaReleaseEvidence $fixture $bad } '*ICache ADS evidence*'
    }
    Write-Fixture 'artifacts/icache_pad_ads.json' ($icacheAds | ConvertTo-Json -Depth 8)
    Assert-FpgaReleaseEvidence $fixture $evidence
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.ddr_route_registration_verified = $false
    Assert-Rejected 'rcf_registration_flag_required' { Assert-FpgaReleaseEvidence $fixture $bad } '*DDR route registration evidence*'
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.ddr_route_target_count = 2
    Assert-Rejected 'rcf_old_two_target_evidence_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*DDR route registration evidence*'
    $checks.Add('portable_release_snapshot_accepted_without_pds_cache')
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.cpu_ads_controls_verified = $false
    Assert-Rejected 'cpu_ads_gate_flag_required' { Assert-FpgaReleaseEvidence $fixture $bad } '*CPU ADS evidence*'
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.report_hashes.'pds/synthesize/soc_top_syn.vm' = 'd' * 64
    Assert-Rejected 'cpu_ads_other_netlist_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*Post-synthesis ADS vm fingerprint*'
    $cpuAds.input_snapshot_sha256 = 'e' * 64
    Write-Fixture 'artifacts/cpu_ads_controls.json' ($cpuAds | ConvertTo-Json -Depth 8)
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
    Assert-Rejected 'cpu_ads_foreign_snapshot_rejected_even_with_new_output_hash' { Assert-FpgaReleaseEvidence $fixture $bad } '*CPU ADS evidence*'
    $cpuAds.input_snapshot_sha256 = $snapshotHash
    Write-Fixture 'artifacts/cpu_ads_controls.json' ($cpuAds | ConvertTo-Json -Depth 8)
    $cpuAds.pma_contract.consumer_cases = 0
    Write-Fixture 'artifacts/cpu_ads_controls.json' ($cpuAds | ConvertTo-Json -Depth 8)
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
    Assert-Rejected 'cpu_ads_rehashed_incomplete_pma_rejected' {
        Assert-FpgaReleaseEvidence $fixture $bad
    } '*four-output PMA contract*'
    $cpuAds.pma_contract.consumer_cases = 4288
    Write-Fixture 'artifacts/cpu_ads_controls.json' ($cpuAds | ConvertTo-Json -Depth 8)
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.inputs.PSObject.Properties.Remove('rtl/CoreTop.sv')
    Assert-Rejected 'omitted_evidence_input_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*input coverage inventory*'
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.outputs.PSObject.Properties.Remove('artifacts/soc_top.sbit')
    Assert-Rejected 'omitted_bitstream_hash_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*output coverage inventory*'
    $bad = $evidence | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $bad.run_id = '0' * 32
    Assert-Rejected 'foreign_run_evidence_rejected' { Assert-FpgaReleaseEvidence $fixture $bad } '*not bound*'
    Test-Mutation 'binary_metadata_link_rejected' 'artifacts/mac_selftest.bin' { Assert-FpgaFirmware $fixture } '*Firmware build metadata*'
    Test-Mutation 'elf_metadata_link_rejected' 'artifacts/mac_selftest.elf' { Assert-FpgaFirmware $fixture } '*Firmware build metadata*'
    $rom = Join-Path $fixture 'artifacts/bootrom.hex'
    $originalRom = [IO.File]::ReadAllBytes($rom)
    try {
        Write-Fixture 'artifacts/bootrom.hex' ("04030202`n" + ("00000000`n" * 32767))
        Assert-Rejected 'rom_binary_semantic_mismatch_rejected' { Assert-FpgaFirmware $fixture } '*does not encode*'
    } finally { [IO.File]::WriteAllBytes($rom, $originalRom) }
    $result = [ordered]@{ mode = 'SYNTHETIC_FIXTURES_ONLY'; status = 'PASS'; count = $checks.Count; checks = @($checks) }
    if ($PythonPath) { $result.pre_pnr_helper_checks = @(Test-IcachePrePnrGate $fixture $PythonPath $PSScriptRoot) }
    if ($ReportPath) {
        $report = [IO.Path]::GetFullPath($ReportPath)
        New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force | Out-Null
        [IO.File]::WriteAllText($report, ($result | ConvertTo-Json -Depth 6) + "`n", [Text.UTF8Encoding]::new($false))
    }
    Write-Output "FPGA_SNAPSHOT_FIXTURES_PASS checks=$($checks.Count) (no PDS or board tests)"
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    if (!$resolved.StartsWith($tempBase + '\fpga_snapshot_fixture_', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe fixture cleanup' }
    if (Test-Path -LiteralPath $resolved) {
        if ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked fixture cleanup root' }
        if (@(Get-ChildItem -LiteralPath $resolved -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        }).Count) { throw 'Refusing fixture cleanup through links' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
