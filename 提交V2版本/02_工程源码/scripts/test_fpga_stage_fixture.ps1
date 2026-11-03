# Shared synthetic stage evidence for read-only release/programming fixtures.
# These bytes are never passed to PDS or treated as measured FPGA evidence.
function New-TestFpgaSkewCells([string]$Label, [string]$Slack,
    [string]$Start = '', [string]$End = '', [string]$Required = '16.000',
    [string]$Actual = '1.000') {
    $cells = @('') * 14
    $cells[0] = $Label; $cells[1] = $Slack
    $cells[4] = $Start; $cells[5] = $End
    $cells[10] = $Required; $cells[11] = $Actual
    return (($cells | ForEach-Object {
        '<data>' + [Security.SecurityElement]::Escape($_) + '</data>'
    }) -join '')
}

function New-TestFpgaMaxSkewReports([string]$FdcPath) {
    $fdcLines = @([IO.File]::ReadAllLines($FdcPath))
    $cdcLimit = Assert-SocCdcBounds ($fdcLines -join "`n")
    $required = $cdcLimit.ToString('0.000', [Globalization.CultureInfo]::InvariantCulture)
    $slack = ($cdcLimit - 1).ToString('0.000', [Globalization.CultureInfo]::InvariantCulture)
    $headers = @('Path','Slack','Logic Levels','High Fanout','Start Point','End Point',
        'Launch Clock','Capture Clock','Clock Skew','Data Delay','Required Skew',
        'Actual Skew','Relative Delay','Relative CPR')
    $headerXml = ($headers | ForEach-Object { '<data>' + $_ + '</data>' }) -join ''
    $tables = [Collections.Generic.List[string]]::new()
    foreach ($corner in @('slow','fast')) {
        $rows = [Collections.Generic.List[string]]::new()
        foreach ($fifo in @('ar','aw','w','r','b')) {
            foreach ($direction in @('wr','rd')) {
                $source = "u_${fifo}_fifo/${direction}_gray"
                $capture = if ($direction -eq 'wr') { "u_${fifo}_fifo/wr_gray_rd1" } else { "u_${fifo}_fifo/rd_gray_wr1" }
                $pattern = '^set_max_skew -from .*' + [regex]::Escape($source) +
                    '.* -to .*' + [regex]::Escape($capture) + '.* ([0-9.]+)\s*$'
                $numbers = @(for ($i = 0; $i -lt $fdcLines.Count; $i++) {
                    if ($fdcLines[$i] -match $pattern) { $i + 1 }
                })
                if ($numbers.Count -ne 1) { throw "Synthetic Max Skew FDC pair is ambiguous: ${fifo}_${direction}" }
                $label = "MaxSkew Path ${required}ns, Line Num $($numbers[0])"
                $branches = [Collections.Generic.List[string]]::new()
                foreach ($branchName in @('skew for max path','skew for min path')) {
                    $paths = [Collections.Generic.List[string]]::new()
                    for ($bit = 0; $bit -lt 5; $bit++) {
                        $base = "u_cpu/u_cpu_wrapper/u_axi_cdc/u_${fifo}_fifo"
                        $launch = "$base/$($direction)_gray[$bit]"
                        $stage1 = "$base/$(if ($direction -eq 'wr') {'wr_gray_rd1'} else {'rd_gray_wr1'})[$bit]"
                        $paths.Add('<row>' + (New-TestFpgaSkewCells 'Path 1' $slack $launch $stage1 $required) + '</row>')
                    }
                    $branches.Add('<row>' + (New-TestFpgaSkewCells $branchName $slack -Required $required) +
                        ($paths -join '') + '</row>')
                }
                $rows.Add('<row>' + (New-TestFpgaSkewCells $label $slack -Required $required) +
                    ($branches -join '') + '</row>')
            }
        }
        $tables.Add('<table id="report_timing_' + $corner +
            '_path_max_skew" title="Max Skew Path" column_number="14"><column_headers>' +
            $headerXml + '</column_headers>' + ($rows -join '') + '</table>')
    }
    return [pscustomobject]@{
        xml = '<?xml version="1.0"?><tables>' + ($tables -join '') + '</tables>'
        rtr = "SYNTHETIC FIXTURE ONLY - not PDS evidence`n| Tcl Command  : report_timing -report_max_skew `n" +
            "Design Summary : All Constraints Met.`n| Output | pds/report_timing/rtr.db`n" +
            "Flow Command: report_timing -report_max_skew `n"
    }
}

function New-TestFpgaStageEvidence([string]$Root, $Snapshot, [string]$SnapshotHash) {
    $runPath = 'pds/input-snapshots/' + $Snapshot.run_id + '/'
    $artifact = {
        param([string]$Name)
        Join-Path $Root ('artifacts/' + $Name)
    }
    $sha = {
        param([string]$Path)
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $writeJson = {
        param([string]$Name, $Value)
        [IO.File]::WriteAllText((& $artifact $Name),
            ($Value | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
    }
    $stageFiles = [ordered]@{
        'preflight_gate.json' = $runPath + 'preflight_gate.json'
        'cpu_sys_cdc_ads_pre.json' = $runPath + 'cpu-sys-cdc-ads.json'
        'cpu_sys_cdc_ads.json' = $runPath + 'cpu-sys-cdc-post-route.json'
        'pds_synth_history.txt' = $runPath + 'synth.impl.tcl'
        'pds_post_history.txt' = 'pds/impl.tcl'
        'pds_synth_project.txt' = $runPath + 'soc_pre_synth.pds'
        'pds_post_project.txt' = 'pds/soc.pds'
        'pds_synth_parse_stdout.txt' = $runPath + 'pds.parse-synth.stdout.log'
        'pds_synth_parse_stderr.txt' = $runPath + 'pds.parse-synth.stderr.log'
        'pds_post_parse_stdout.txt' = $runPath + 'pds.parse-post.stdout.log'
        'pds_post_parse_stderr.txt' = $runPath + 'pds.parse-post.stderr.log'
        'pds_synth_stdout.txt' = $runPath + 'pds.synth.stdout.log'
        'pds_synth_stderr.txt' = $runPath + 'pds.synth.stderr.log'
        'pds_post_stdout.txt' = $runPath + 'pds.stdout.log'
        'pds_post_stderr.txt' = $runPath + 'pds.stderr.log'
        'pds_synth_constraints.txt' = $runPath + 'synth.constraint_check.ccr'
        'pds_post_constraints.txt' = 'pds/constraint_check/constraint_check.ccr'
        'pds_post_map_constraints.txt' = 'pds/device_map/soc_top.dmr'
        'pds_synth_flow.txt' = $runPath + 'synth.flow.log'
        'synth_resource_report.txt' = 'pds/synthesize/soc_top.snr'
        'final_timing_report.txt' = 'pds/report_timing/soc_top.rtr'
        'final_timing_xml.xml' = 'pds/report_timing/rtr.db'
    }
    $fdcLines = @([IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc')) -split '\r?\n')
    $dmrLines = @($fdcLines | Where-Object {
        $_ -match '^create_clock -name \{(?:sys|cpu)_clk\} ' -or
        ($_ -match '^set_(?:max_delay|max_skew|false_path)\b' -and
            ($_.Contains('u_axi_cdc') -or $_.Contains('u_irq_sync')))
    })
    [IO.File]::WriteAllText((& $artifact 'pds_post_map_constraints.txt'),
        ($dmrLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    $cdc = [ordered]@{
        schema = 1; status = 'PASS'; run_id = $Snapshot.run_id
        snapshot_sha256 = $SnapshotHash; vm_sha256 = 'c' * 64; adf_sha256 = 'a' * 64
        ccr_sha256 = & $sha (& $artifact 'pds_post_constraints.txt')
        fdc_sha256 = $Snapshot.inputs['pds/soc.fdc']
        constraints = @{ total_constraints = 1171; cdc_directives = 48
            gray_directives = 30; payload_directives = 10; first_stage_directives = 8
            mapped_endpoint_tags = 300; mapped_payload_output_tags = 298
            mapped_first_stage_tags = 8; mapped_second_stage_tags = 4
            errors = 0; critical_warnings = 39; warnings = 0 }
        fifos = @(foreach ($fifo in @('ar','aw','w','r','b')) {
            foreach ($direction in @('wr','rd')) {
                $base = "u_cpu/u_cpu_wrapper/u_axi_cdc/u_${fifo}_fifo"
                $launch = "$base/$($direction)_gray[4:0]"
                $capture = "$base/$(if ($direction -eq 'wr') {'wr_gray_rd1'} else {'rd_gray_wr1'})[4:0]"
                $match = @{ launch_vector_objects = 1; capture_vector_objects = 1
                    launch_object = $launch; capture_object = $capture }
                @{ fifo = $fifo; direction = $direction; mapped_launch_ff = 5
                    mapped_stage1_ff = 5; mapped_stage2_ff = 5; pap_preserve = $true
                    fdc_matches = @{ max_delay = $match; max_skew = $match; hold_cut = $match }
                }
            }
        })
        payloads = @(foreach ($fifo in @('ar','aw','w','r','b')) {
            $spec = switch ($fifo) {
                'ar' { @{launch='cpu_clk'; clock='sys_clk'; x1=0; x2=19} }
                'aw' { @{launch='cpu_clk'; clock='sys_clk'; x1=1; x2=18} }
                'w'  { @{launch='cpu_clk'; clock='sys_clk'; x1=1; x2=18} }
                'r'  { @{launch='sys_clk'; clock='cpu_clk'; x1=0; x2=18} }
                'b'  { @{launch='sys_clk'; clock='cpu_clk'; x1=1; x2=0} }
            }
            $cellCount = $spec.x1 + $spec.x2
            $base = "u_cpu/u_cpu_wrapper/u_axi_cdc/u_${fifo}_fifo/storage"
            $match = @{ launch_array_objects = 1; launch_object = $base
                capture_clock = $spec.clock }
            @{ fifo = $fifo; launch_clock = $spec.launch; capture_clock = $spec.clock; mapped_ram_cells = $cellCount
                mapped_ram_x1dp = $spec.x1; mapped_ram_x2dp = $spec.x2
                mapped_do_outputs = $spec.x1 + 2 * $spec.x2
                mapped_ram_instances = @(for ($index = 0; $index -lt $cellCount; $index++) {
                    if ($index -eq 0) { 'storage' } else { "storage_$index" }
                })
                fdc_matches = @{ max_delay = $match; hold_cut = $match }
            }
        })
        first_stage_crossings = @(
            @{ name='cpu_ready_sys0'; source_clock='cpu_clk'; capture_clock='sys_clk'
                capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/cpu_ready_sys[1:0]'
                mapped_first_stage_ff=1; mapped_second_stage_ff=1; mapped_second_stage_tags=2
                second_stage_source_clock_filtered=$true
                fdc_matches=@{ max_delay=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/cpu_ready_sys[1:0]'; source_clock='cpu_clk' }
                    hold_cut=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/cpu_ready_sys[1:0]'; source_clock='cpu_clk' } } }
            @{ name='sys_ready_cpu0'; source_clock='sys_clk'; capture_clock='cpu_clk'
                capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/sys_ready_cpu[1:0]'
                mapped_first_stage_ff=1; mapped_second_stage_ff=1; mapped_second_stage_tags=2
                second_stage_source_clock_filtered=$true
                fdc_matches=@{ max_delay=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/sys_ready_cpu[1:0]'; source_clock='sys_clk' }
                    hold_cut=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_axi_cdc/sys_ready_cpu[1:0]'; source_clock='sys_clk' } } }
            @{ name='timer_c1'; source_clock='sys_clk'; capture_clock='cpu_clk'
                capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1'
                mapped_first_stage_ff=1; mapped_second_stage_ff=1; mapped_second_stage_tags=0
                second_stage_source_clock_filtered=$true
                fdc_matches=@{ max_delay=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1'; source_clock='sys_clk' }
                    hold_cut=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1'; source_clock='sys_clk' } } }
            @{ name='software_c1'; source_clock='sys_clk'; capture_clock='cpu_clk'
                capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/software_c1'
                mapped_first_stage_ff=1; mapped_second_stage_ff=1; mapped_second_stage_tags=0
                second_stage_source_clock_filtered=$true
                fdc_matches=@{ max_delay=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/software_c1'; source_clock='sys_clk' }
                    hold_cut=@{ capture_ff_objects=1
                        capture_object='u_cpu/u_cpu_wrapper/u_irq_sync/software_c1'; source_clock='sys_clk' } } }
        )
        single_bit_synchronizers = @(
            @{ name='cpu_ready_sys'; capture_clock='sys_clk'; stages=2; pap_preserve=$true; first_stage_source='cpu_ready_sys' }
            @{ name='sys_ready_cpu'; capture_clock='cpu_clk'; stages=2; pap_preserve=$true; first_stage_source='sys_ready_cpu' }
            @{ name='timer_irq'; capture_clock='cpu_clk'; stages=2; pap_preserve=$true; first_stage_source='timer_irq_sys' }
            @{ name='software_irq'; capture_clock='cpu_clk'; stages=2; pap_preserve=$true; first_stage_source='software_irq_sys' }
            @{ name='external_irq'; capture_clock='cpu_clk'; stages=2; pap_preserve=$true; first_stage_source="1'b0" }
        )
    }
    & $writeJson 'cpu_sys_cdc_ads.json' $cdc
    & $writeJson 'cpu_sys_cdc_ads_pre.json' $cdc
    $reports = @{
        'pds/synthesize/soc_top_syn.vm' = 'c' * 64
        'pds/synthesize/soc_top_syn.adf' = 'a' * 64
        ($runPath + 'soc_pre_synth.pds') = & $sha (& $artifact 'pds_synth_project.txt')
        ($runPath + 'cpu-pre-pnr.json') = & $sha (& $artifact 'cpu_ads_controls.json')
        ($runPath + 'icache-pad-pre-pnr.json') = & $sha (& $artifact 'icache_pad_ads.json')
        ($runPath + 'cpu-sys-cdc-ads.json') = & $sha (& $artifact 'cpu_sys_cdc_ads_pre.json')
        'pds/soc.pds' = 'f' * 64
        'pds/place_route/soc_top_pnr.netlist' = 'f' * 64
    }
    $synthHashes = [ordered]@{
        'pds/synthesize/soc_top.snr' = & $sha (& $artifact 'synth_resource_report.txt')
        'pds/synthesize/soc_top_syn.vm' = 'c' * 64
        'pds/synthesize/soc_top_syn.adf' = 'a' * 64
        ($runPath + 'synth.constraint_check.ccr') = & $sha (& $artifact 'pds_synth_constraints.txt')
    }
    $preflight = [ordered]@{
        schema = 1; status = 'PASS'; run_id = $Snapshot.run_id
        input_snapshot_sha256 = $SnapshotHash; synth_hashes = $synthHashes
        cdc_summary = @{ total_constraints = 1171; errors = 0; critical_warnings = 39
            warnings = 0; mapped_directions = 10; payload_ram_cells = 76
            payload_do_outputs = 149; first_stage_crossings = 4
            vector_match_each = 1; mapped_ff_each = 5 }
        synth_history_sha256 = & $sha (& $artifact 'pds_synth_history.txt')
        synth_project_sha256 = $reports[$runPath + 'soc_pre_synth.pds']
        cpu_ads_sha256 = $reports[$runPath + 'cpu-pre-pnr.json']
        icache_ads_sha256 = $reports[$runPath + 'icache-pad-pre-pnr.json']
        cdc_ads_sha256 = $reports[$runPath + 'cpu-sys-cdc-ads.json']
    }
    & $writeJson 'preflight_gate.json' $preflight
    foreach ($entry in $stageFiles.GetEnumerator()) {
        $reports[$entry.Value] = & $sha (& $artifact $entry.Key)
    }
    $reports[$runPath + 'post.soc_top.dmr'] = $reports['pds/device_map/soc_top.dmr']
    [pscustomobject]@{
        reports = $reports
        preflight_sha256 = $reports[$runPath + 'preflight_gate.json']
        cdc_sha256 = $reports[$runPath + 'cpu-sys-cdc-post-route.json']
        synth_hashes = $synthHashes
    }
}
