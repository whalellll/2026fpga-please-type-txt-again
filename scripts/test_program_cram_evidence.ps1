param([string]$ReportPath = '')
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'test_icache_pad_fixture.ps1')
. (Join-Path $PSScriptRoot 'test_fpga_stage_fixture.ps1')
$tempBase = [IO.Path]::GetFullPath((Join-Path $sourceRoot 'build/cram-evidence-tests')).TrimEnd('\')
New-Item -ItemType Directory -Path $tempBase -Force | Out-Null
$fixtureBase = Join-Path $tempBase ('cram_evidence_fixture_' + [guid]::NewGuid().ToString('N'))
$fixture = Join-Path $fixtureBase 'project'
$fakePds = Join-Path $fixtureBase 'fake-pds'
$checks = [Collections.Generic.List[object]]::new()
$outputs = [Collections.Generic.List[string]]::new()
$protected = Get-FpgaHashMap $sourceRoot (Get-FpgaInputPaths $sourceRoot)
foreach ($relative in @('scripts/program_cram.ps1', 'scripts/test_program_cram_evidence.ps1', 'docs/BUILD.md')) {
    if ($protected.Contains($relative)) { throw "Test/edit would touch a frozen FPGA input: $relative" }
}
# No fixture is allowed to reach a hardware/tool launch, even after regression.
function Start-Process { throw 'FIXTURE_FORBIDS_PROCESS_START' }
function Get-NetTCPConnection { throw 'FIXTURE_FORBIDS_NETWORK_OR_JTAG_ACCESS' }
function Write-Fixture([string]$Relative, [string]$Text) {
    $path = Get-FpgaSafePath $fixture $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, $Text, [Text.UTF8Encoding]::new($false))
}
function Invoke-DryCase([string]$Name, [hashtable]$Arguments, [string]$ExpectedFailure = '') {
    $failure = ''; $messages = @()
    try {
        $messages = @(& (Join-Path $fixture 'scripts/program_cram.ps1') -DryRun -PdsRoot $fakePds @Arguments *>&1 | ForEach-Object { "$_" })
    } catch { $failure = $_.Exception.Message }
    $text = $messages -join "`n"
    if ($ExpectedFailure) {
        if ($failure -notlike $ExpectedFailure) { throw "${Name}: expected '$ExpectedFailure', got '$failure'" }
    } elseif ($failure -or !$text.Contains('DRY_RUN_PASS:')) {
        throw "${Name}: expected DryRun PASS, got '$failure' / '$text'"
    }
    $outputs.Add("CASE $Name`n$text`nREJECTION $failure")
    $checks.Add([ordered]@{ name = $Name; status = 'PASS'; actual_rejection = $failure })
    return $text
}
function Test-Mutation([string]$Name, [string]$Relative, [string]$ExpectedFailure, [hashtable]$Arguments = @{}) {
    $path = Get-FpgaSafePath $fixture $Relative
    $bytes = [IO.File]::ReadAllBytes($path)
    $mtime = [IO.File]::GetLastWriteTimeUtc($path)
    try {
        [IO.File]::AppendAllText($path, "`nchanged", [Text.UTF8Encoding]::new($false))
        [IO.File]::SetLastWriteTimeUtc($path, $mtime)
        $null = Invoke-DryCase $Name $Arguments $ExpectedFailure
    } finally { [IO.File]::WriteAllBytes($path, $bytes) }
}
try {
    foreach ($directory in @('config','docs','rtl','sw','sim','ip','scripts','linux/boot','prebuilt','artifacts','pds','skills')) {
        New-Item -ItemType Directory -Path (Join-Path $fixture $directory) -Force | Out-Null
    }
    foreach ($name in @('README.md','AGENTS.md','CHANGELOG.md','.gitignore','.gitattributes')) {
        Write-Fixture $name 'SYNTHETIC FIXTURE ONLY; no synthesis or board result.'
    }
    Write-Fixture 'SKILLS_DELIVERY.json' '{"scope":"SYNTHETIC_FIXTURE_ONLY"}'
    Write-Fixture 'VERSION' '6.1'
    foreach ($name in @('program_cram.ps1','pds_program_cram.tcl','pds_scan_chain.tcl',
        'audit_project.ps1','build_snapshot.ps1','project_files.ps1','riscv_toolchain.ps1',
        'release_version.ps1','check_clock_config.ps1','clock_policy.ps1','timing_scope.ps1','export_release_docx.py')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $fixture "scripts/$name")
    }
    # Only the physical project's preparation step is a fixture stub. The actual
    # project audit, firmware/snapshot/hash/STA checks and CRAM script run intact.
    Write-Fixture 'scripts/prepare_pds_project.ps1' 'param([switch]$ValidateOnly) if (!$ValidateOnly) { throw "SYNTHETIC_FIXTURE_VALIDATE_ONLY" }'
    Write-Fixture 'scripts/build_fpga.ps1' '# SYNTHETIC fixture build recipe; never invoked'
    Write-Fixture 'scripts/audit_cpu_ads.py' '# SYNTHETIC fixture ADS recipe; never invoked'
    Write-Fixture 'scripts/audit_icache_pad_ads.py' '# SYNTHETIC fixture ICache ADS recipe; never invoked'
    $consoleDoc = @(Get-ChildItem -LiteralPath (Join-Path $sourceRoot 'docs') -Filter 'console*.md' -File)
    if ($consoleDoc.Count -ne 1) { throw 'Missing current console document for fixture' }
    $docxSources = @('README.md','CHANGELOG.md','docs/ARCHITECTURE.md','docs/BUILD.md',
        'docs/COREMARK.md','docs/Validation.md','docs/SUPPORTED_HARDWARE.md',
        ('docs/' + $consoleDoc[0].Name))
    foreach ($name in $docxSources | Where-Object { $_ -notin @('README.md','CHANGELOG.md') }) {
        Write-Fixture $name 'SYNTHETIC fixture documentation only'
    }
    Write-Fixture 'docs/SOC_linux_V6.1.docx' 'SYNTHETIC fixture DOCX; no release content'
    $docxHashes = [ordered]@{}
    foreach ($name in $docxSources) {
        $docxHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $fixture $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Write-Fixture 'docs/SOC_linux_V6.1.docx.inputs.json' ([ordered]@{
        schema = 1
        generator_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture 'scripts/export_release_docx.py') -Algorithm SHA256).Hash.ToLowerInvariant()
        source_sha256 = $docxHashes
        docx_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture 'docs/SOC_linux_V6.1.docx') -Algorithm SHA256).Hash.ToLowerInvariant()
    } | ConvertTo-Json -Depth 5)
    Write-Fixture 'rtl/cpu/CoreTop.sv' '// SYNTHETIC CPU source; never synthesized'
    Write-Fixture 'rtl/cpu/emit-config.json' '{"scope":"SYNTHETIC_ONLY"}'
    Write-Fixture 'rtl/cpu/source.json' '{"scope":"SYNTHETIC_ONLY","cpu":"CPU V3.1","cpu_version":"3.1.0"}'
    Copy-Item -LiteralPath (Join-Path $sourceRoot 'config/clocks.json') -Destination (Join-Path $fixture 'config/clocks.json')
    if (Test-Path -LiteralPath (Join-Path $sourceRoot 'config/display.json') -PathType Leaf) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot 'config/display.json') -Destination (Join-Path $fixture 'config/display.json')
    }
    Copy-Item -LiteralPath (Join-Path $sourceRoot 'config/timing_scope_baseline.json') -Destination (Join-Path $fixture 'config/timing_scope_baseline.json')
    $fixtureClocks = Get-Content -LiteralPath (Join-Path $sourceRoot 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Fixture 'sw/bootloader/release_version.h' "#ifndef SOC_RELEASE_VERSION_H`n#define SOC_RELEASE_VERSION_H`n#define SOC_RELEASE_VERSION `"V6.1`"`n#define CPU_RELEASE_VERSION `"V3.1`"`n#endif`n"
    Write-Fixture 'sw/bootloader/soc.h' "#define SYS_CLOCK_HZ $($fixtureClocks.sys_hz)u`n#define CPU_CLOCK_HZ $($fixtureClocks.cpu_hz)u`n#define TIMEBASE_HZ $($fixtureClocks.timebase_hz)u`n"
    Write-Fixture 'sw/coremark/core_portme.h' "#define CORE_CLOCKS_PER_SEC $($fixtureClocks.timebase_hz)ULL`n"
    # Keep the text-only clock audit coherent with the selected config/FDC.
    # In particular, a dedicated CPU PLL cannot use the old video891 formula.
    # These sources are audited only: process/network launch guards remain active.
    foreach ($relative in @('rtl/soc/soc_top.v','rtl/video/pll_video.v','rtl/video/pll_cpu.v')) {
        Write-Fixture $relative ([IO.File]::ReadAllText((Join-Path $sourceRoot $relative)))
    }
    Write-Fixture 'sim/tb_cpu_integration.sv' "integer coremark_cpu_hz = $($fixtureClocks.cpu_hz);`n"
    foreach ($name in @('coremark_fixed_bootloader.ps1','run_coremark_production_sim.ps1','measure_coremark.ps1')) {
        Write-Fixture "scripts/$name" ('[ValidateRange(1, 1000000000)][int]$CpuHz = ' + $fixtureClocks.cpu_hz + "`n")
    }
    Write-Fixture 'sw/main.c' '/* SYNTHETIC source */'
    Write-Fixture 'ip/fixture.idf' 'SYNTHETIC'
    Write-Fixture 'linux/soc.dts' "PG2L100H SoC Linux HID+XQ reserved-memory framebuffer-dma@1fe11000 framebuffer@1b200000`nclock-frequency = <$($fixtureClocks.cpu_hz)>;`ntimebase-frequency = <$($fixtureClocks.timebase_hz)>;`n"
    Write-Fixture 'linux/boot/soc.dtb' 'PG2L100H SoC Linux HID+XQ'
    Write-Fixture 'pds/soc.tcl' ('compile' + [Environment]::NewLine + 'synthesize')
    Write-Fixture 'pds/soc_post_synth.tcl' ('dev_map -input_db_file "synthesize/soc_top_syn.adf"' +
        [Environment]::NewLine + 'pnr -fix_hold_violation -optimize_multi_corner_timing' +
        [Environment]::NewLine + 'report_timing -report_max_skew' + [Environment]::NewLine + 'gen_bit_stream')
    Write-Fixture 'pds/soc_gui.pds' 'SYNTHETIC GUI; not opened by tools'
    Copy-Item -LiteralPath (Join-Path $sourceRoot 'pds/soc.fdc') -Destination (Join-Path $fixture 'pds/soc.fdc') -Force
    Write-Fixture 'pds/audit_cpu_sys_cdc_ads.py' '# SYNTHETIC CDC audit; never invoked by a tool'
    Write-Fixture 'pds/ddr3_test.rcf' ((Get-FpgaDdrRouteLines) -join "`n")
    Write-Fixture 'artifacts/SONG.PCM' 'SYNTHETIC'
    . (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
    $markers = 'SoC V6.1 bootloader debug camera debug camera_sd Photo saved and verified on SD. Camera busy; Photo saved by PC. debug speaker debug mic SONG.PCM'
    foreach ($name in Get-FpgaFirmwareNames) {
        $bytes = if ($name -eq 'bootloader') { [Text.Encoding]::ASCII.GetBytes($markers) } else { [byte[]]@(1,2,3,4) }
        [IO.File]::WriteAllBytes((Join-Path $fixture "artifacts/$name.bin"), $bytes)
        [IO.File]::WriteAllBytes((Join-Path $fixture "artifacts/$name.elf"), [byte[]]@(127,69,76,70,1,2,3,4))
        Write-Fixture "artifacts/$name.build.json" ([ordered]@{
            scope = 'SYNTHETIC_ONLY'; binary = "$name.bin"
            binary_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture "artifacts/$name.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
            compiler_target = $CpuTarget; compiler_version = $CpuGccVersion; march = $CpuMarch; abi = $CpuAbi; optimization = '-O2'
            compiler_sha256 = 'a' * 64
            elf_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixture "artifacts/$name.elf") -Algorithm SHA256).Hash.ToLowerInvariant()
            elf_metadata = @{ ElfClass = 'ELF32'; Flags = '0x0 (synthetic)' }
            code_validation = @{ Result = 'RV32IMA mnemonic/width whitelist synthetic'; BytesChecked = 4; ExplicitIllegalInstructionFixture = $false }
        } | ConvertTo-Json -Depth 5)
    }
    $padded = New-Object byte[] 131072
    $boot = [IO.File]::ReadAllBytes((Join-Path $fixture 'artifacts/bootloader.bin'))
    [Array]::Copy($boot, $padded, $boot.Length)
    $rom = for ($i = 0; $i -lt 32768; $i++) { [BitConverter]::ToUInt32($padded, $i * 4).ToString('x8') }
    Write-Fixture 'artifacts/bootrom.hex' (($rom -join "`n") + "`n")
    $assets = Get-FpgaStagedAssets
    foreach ($relative in $assets.Keys) {
        if (!(Test-Path -LiteralPath (Join-Path $fixture $assets[$relative]))) { Write-Fixture $assets[$relative] 'SYNTHETIC init data' }
        Write-Fixture $relative ([IO.File]::ReadAllText((Join-Path $fixture $assets[$relative])))
    }
    $snapshot = New-FpgaSnapshot $fixture
    Copy-Item -LiteralPath (Join-Path $fixture 'pds/build_snapshot.json') -Destination (Join-Path $fixture 'artifacts/build_snapshot.json')
    foreach ($name in @('soc_top.sbit','soc_top.bin','timing_summary.txt','SHA256SUMS.txt')) {
        Write-Fixture "artifacts/$name" 'SYNTHETIC FIXTURE ONLY - not usable as FPGA evidence or bitstream'
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
    Write-Fixture 'artifacts/cpu_ads_controls.json' ([ordered]@{
        schema_version = 1; status = 'PASS'; scope = 'SYNTHETIC_ONLY'
        frontend_cases = 85760; pma_address_cases = 2144; rsmem_hint_cases = 17152
        input_snapshot_sha256 = $snapshotHash; input_snapshot_run_id = $snapshot.run_id
        cpu_rtl_sha256 = $snapshot.inputs['rtl/cpu/CoreTop.sv']; cpu_emit_config_sha256 = $snapshot.inputs['rtl/cpu/emit-config.json']
        production_rom_sha256 = $snapshot.inputs['artifacts/bootrom.hex']; audit_script_sha256 = $snapshot.inputs['scripts/audit_cpu_ads.py']; netlist_sha256 = 'c' * 64
        pma_contract = [ordered]@{
            address_cases = 2144; consumer_cases = 4288
            consumers = @('Lsu.N13', 'Lsu.N965')
            mapped_outputs = [ordered]@{ _N1=@{}; _N2=@{}; _N3=@{}; _N4=@{} }
            consumer_pma_inputs = [ordered]@{ N13=@('_N2','_N3','_N4'); N965=@('_N1') }
            output_values = [ordered]@{ _N1=@(0,1); _N2=@(0,1); _N3=@(0,1); _N4=@(0,1) }
        }
    } | ConvertTo-Json -Depth 8)
    Write-Fixture 'artifacts/icache_pad_ads.json' ((New-TestIcachePadEvidence $snapshot $snapshotHash ('c' * 64)) | ConvertTo-Json -Depth 8)
    $icacheHash = (Get-FileHash -LiteralPath (Join-Path $fixture 'artifacts/icache_pad_ads.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $stage = New-TestFpgaStageEvidence $fixture $snapshot $snapshotHash
    $evidence = [ordered]@{
        schema = 3; scope = 'SYNTHETIC_ONLY'; release = 'V6.1'; device = 'PG2L100H-6-FBG676'
        timing = 'All Constraints Met'; timing_summary_source = 'final report_timing'; latches = 0
        snapshot_registers_verified = $true; pins_verified = $true; sd_write_registers_verified = $true
        sd_multiblock_registers_verified = $true; hud_registers_verified = $true; cpu_ads_controls_verified = $true
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
        run_id = $snapshot.run_id; started_utc = $snapshot.started_utc; completed_utc = ([datetime]::Parse($snapshot.started_utc)).AddSeconds(1).ToString('o')
        input_snapshot_sha256 = $snapshotHash; inputs = $snapshot.inputs; outputs = Get-FpgaHashMap $fixture (Get-FpgaOutputPaths)
        ddr_route_registration_verified = $true; ddr_route_constraint_sha256 = $snapshot.inputs['pds/ddr3_test.rcf']; ddr_route_target_count = @(Get-FpgaDdrRouteLines).Count
        report_hashes = $stage.reports
    }
    $evidenceText = $evidence | ConvertTo-Json -Depth 7
    Write-Fixture 'artifacts/build_evidence.json' $evidenceText
    New-Item -ItemType Directory -Path (Join-Path $fakePds 'bin') -Force | Out-Null
    foreach ($name in @('cdt_js.exe','cdt_cfg_shell.exe')) { [IO.File]::WriteAllText((Join-Path $fakePds "bin/$name"), 'NOT EXECUTABLE: DRY-RUN FIXTURE ONLY') }
    $passText = Invoke-DryCase 'matching_current_synthetic_build' @{}
    if (!$passText.Contains('SOC_PROJECT_AUDIT_PASS') -or !$passText.Contains('current project snapshot, CPU/ROM, final STA and selected bitstream match.')) { throw 'Actual project audit did not execute' }
    $null = Invoke-DryCase 'explicit_repository_image_still_audited' @{ SbitPath = (Join-Path $fixture 'artifacts/soc_top.sbit'); AllowExternalSbit = $true }
    $null = Invoke-DryCase 'cpu80_profile_rejects_another_build' @{ AuditProfile = 'CPU80Approved' } '*CPU80Approved audit requires the exact CPU80 run and bitstream*'
    Test-Mutation 'changed_cpu_with_old_mtime_rejected' 'rtl/cpu/CoreTop.sv' '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'changed_rom_with_old_mtime_rejected' 'artifacts/bootrom.hex' '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'changed_icache_checker_with_old_mtime_rejected' 'scripts/audit_icache_pad_ads.py' '*Frozen FPGA inputs mismatch*'
    Test-Mutation 'changed_icache_evidence_rejected' 'artifacts/icache_pad_ads.json' '*Build evidence output coverage mismatch*'
    Test-Mutation 'changed_max_skew_xml_rejected' 'artifacts/final_timing_xml.xml' '*Build evidence output coverage mismatch*'
    $icachePath = Join-Path $fixture 'artifacts/icache_pad_ads.json'
    $icacheBytes = [IO.File]::ReadAllBytes($icachePath)
    try {
        Remove-Item -LiteralPath $icachePath
        $null = Invoke-DryCase 'missing_icache_evidence_rejected' @{} '*Missing release file: artifacts/icache_pad_ads.json*'
        [IO.File]::WriteAllBytes($icachePath, $icacheBytes)
        $evidence.icache_pad_ads_verified = $false
        Write-Fixture 'artifacts/build_evidence.json' ($evidence | ConvertTo-Json -Depth 7)
        $null = Invoke-DryCase 'icache_flag_required_before_programming' @{} '*ICache ADS evidence flag*'
        $evidence.icache_pad_ads_verified = $true
    } finally {
        [IO.File]::WriteAllBytes($icachePath, $icacheBytes)
        Write-Fixture 'artifacts/build_evidence.json' $evidenceText
    }
    Test-Mutation 'changed_canonical_bitstream_rejected' 'artifacts/soc_top.sbit' '*Build evidence output coverage mismatch*'
    Test-Mutation 'external_flag_does_not_bypass_changed_default_image' 'artifacts/soc_top.sbit' '*Build evidence output coverage mismatch*' @{ AllowExternalSbit = $true }
    Write-Fixture 'artifacts/other.sbit' 'Different SYNTHETIC bitstream'
    $null = Invoke-DryCase 'different_selected_repository_bitstream_rejected' @{ SbitPath = (Join-Path $fixture 'artifacts/other.sbit') } '*Selected .sbit does not match*'
    Remove-Item -LiteralPath (Join-Path $fixture 'artifacts/other.sbit')
    $snapshotPath = Join-Path $fixture 'artifacts/build_snapshot.json'
    $snapshotBytes = [IO.File]::ReadAllBytes($snapshotPath)
    try {
        Remove-Item -LiteralPath $snapshotPath
        $null = Invoke-DryCase 'missing_snapshot_rejected_before_tool_start' @{} '*Missing release file: artifacts/build_snapshot.json*'
        $external = Join-Path $fixtureBase 'independent.sbit'
        [IO.File]::WriteAllText($external, 'Independent SYNTHETIC bitstream')
        $externalText = Invoke-DryCase 'explicit_external_image_without_project_snapshot' @{ SbitPath = $external; AllowExternalSbit = $true }
        if (!$externalText.Contains('no current project CPU/ROM/STA match is asserted.')) { throw 'External image scope is not explicit' }
        $null = Invoke-DryCase 'external_path_without_existing_opt_in_rejected' @{ SbitPath = $external } '*Use -AllowExternalSbit only*'
    } finally { [IO.File]::WriteAllBytes($snapshotPath, $snapshotBytes) }
    try {
        $oldSnapshot = [Text.Encoding]::UTF8.GetString($snapshotBytes) | ConvertFrom-Json
        $oldSnapshot.release = 'V5.4'
        Write-Fixture 'artifacts/build_snapshot.json' ($oldSnapshot | ConvertTo-Json -Depth 7)
        $null = Invoke-DryCase 'historical_snapshot_rejected' @{} '*Missing, obsolete, or foreign FPGA start snapshot*'
    } finally { [IO.File]::WriteAllBytes($snapshotPath, $snapshotBytes) }
    try {
        $evidence.release = 'V5.4'
        Write-Fixture 'artifacts/build_evidence.json' ($evidence | ConvertTo-Json -Depth 7)
        $null = Invoke-DryCase 'historical_release_rejected' @{} '*Current release build evidence is missing or incomplete*'
        $null = Invoke-DryCase 'external_flag_does_not_bypass_historical_default' @{ AllowExternalSbit = $true } '*Current release build evidence is missing or incomplete*'
        $evidence.release = 'V6.1'; $evidence.timing = 'Some Constraints Violated'
        Write-Fixture 'artifacts/build_evidence.json' ($evidence | ConvertTo-Json -Depth 7)
        $null = Invoke-DryCase 'sta_fail_rejected' @{} '*Current release build evidence is missing or incomplete*'
    } finally { Write-Fixture 'artifacts/build_evidence.json' $evidenceText }
    Assert-FpgaMap $protected (Get-FpgaHashMap $sourceRoot (Get-FpgaInputPaths $sourceRoot)) 'Production inputs changed during CRAM fixture tests'
    $result = [ordered]@{
        schema = 1; mode = 'ISOLATED_SYNTHETIC_DRYRUN_ONLY'; status = 'PASS'; count = $checks.Count; checks = @($checks)
        actual_helpers = @('program_cram.ps1','audit_project.ps1','build_snapshot.ps1','project_files.ps1','riscv_toolchain.ps1')
        stub_scope = 'Only prepare_pds_project.ps1 is a ValidateOnly fixture stub; no physical project preparation, PDS or board acceptance is claimed'
        hardware_tools_started = $false; program_or_scanonly_invoked = $false; unchanged_production_fpga_inputs = $protected.Count
        script_hashes = [ordered]@{}
    }
    foreach ($name in $result.actual_helpers + @('test_program_cram_evidence.ps1')) { $result.script_hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
    if ($ReportPath) {
        $report = [IO.Path]::GetFullPath($ReportPath)
        New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force | Out-Null
        $outputPath = [IO.Path]::ChangeExtension($report, '.output.txt')
        [IO.File]::WriteAllText($outputPath, ($outputs -join "`n`n") + "`n", [Text.UTF8Encoding]::new($false))
        $result.raw_output_file = [IO.Path]::GetFileName($outputPath)
        $result.raw_output_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText($report, ($result | ConvertTo-Json -Depth 7) + "`n", [Text.UTF8Encoding]::new($false))
    }
    Write-Output "CRAM_EVIDENCE_FIXTURES_PASS cases=$($checks.Count) production_inputs=$($protected.Count) NO_HARDWARE_TOOLS"
} finally {
    $resolved = [IO.Path]::GetFullPath($fixtureBase)
    if (!$resolved.StartsWith($tempBase + '\cram_evidence_fixture_', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe fixture cleanup path' }
    if (Test-Path -LiteralPath $resolved) {
        if ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint -or
            @(Get-ChildItem -LiteralPath $resolved -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Refusing fixture cleanup through reparse points' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
