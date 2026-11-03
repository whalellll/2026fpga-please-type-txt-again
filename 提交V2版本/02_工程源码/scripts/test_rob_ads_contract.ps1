param([string]$ReportPath = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
# Deliberately synthetic evidence; this test never launches PDS or opens hardware.
$snapshot = [pscustomobject]@{
    release = 'V6.5'; run_id = 'a' * 32
    inputs = [pscustomobject]@{
        'scripts/audit_rob_owner_ads.py' = 'a' * 64
        'rtl/cpu/CoreTop.sv' = 'b' * 64
        'rtl/cpu/source.json' = 'c' * 64
        'rtl/cpu/emit-config.json' = 'd' * 64
    }
}
$cpu = [pscustomobject]@{
    input_snapshot_sha256 = 'e' * 64; netlist_sha256 = 'f' * 64
    rob_owner_contract = [pscustomobject]@{
        schema = 1; status = 'PASS'; scope = 'MAPPED_ROB_C1_LIMITED'
        run_id = 'a' * 32; input_snapshot_sha256 = 'e' * 64; vm_sha256 = 'f' * 64
        checker_sha256 = 'a' * 64; cpu_rtl_sha256 = 'b' * 64
        cpu_source_json_sha256 = 'c' * 64; cpu_emit_config_sha256 = 'd' * 64
        tag_live_ff = 32; result_valid_ff = 32; owner_tags = 32; owner_ff = 96
        disabled_interface_port = 3
        owner_cones = @(0..95 | ForEach-Object { "synthetic_owner_$_" })
        owner_clear_dependency_absent = $true; owner_hierarchy_nodes = 1
        owner_hierarchy_boundary_leaves = @('synthetic/wb')
        read_port_bindings = @(0..27 | ForEach-Object { "synthetic_binding_$_" })
        local_read_checks = @(
            @{ tag_lane=2; bank_read_port=4; tested_data_bit=0; checked_vectors=512; nonconstant_bits=32 },
            @{ tag_lane=4; bank_read_port=2; tested_data_bit=0; checked_vectors=512; nonconstant_bits=32 }
        )
        full_sequential_equivalence_proven = $false; routed_timing_or_board_proven = $false
        banks = @(0..3 | ForEach-Object {
            [pscustomobject]@{ bank = $_; source_port = @(0,1,2,4)[$_]; checked_vectors = 1536; write_enable = "fixture_we$_" }
        })
    }
}
$checks = [Collections.Generic.List[string]]::new()
Assert-FpgaRobOwnerContract $cpu $snapshot
$checks.Add('matching_v65_limited_contract_accepted')
foreach ($mutation in @(
    @{ name='old_evidence_without_rob'; action={param($c) $c.rob_owner_contract=$null} },
    @{ name='foreign_run'; action={param($c) $c.rob_owner_contract.run_id='b'*32} },
    @{ name='wrong_vm'; action={param($c) $c.rob_owner_contract.vm_sha256='1'*64} },
    @{ name='wrong_checker'; action={param($c) $c.rob_owner_contract.checker_sha256='2'*64} },
    @{ name='wrong_cpu_source'; action={param($c) $c.rob_owner_contract.cpu_source_json_sha256='3'*64} },
    @{ name='missing_owner'; action={param($c) $c.rob_owner_contract.owner_ff=95} },
    @{ name='missing_owner_clear_check'; action={param($c) $c.rob_owner_contract.owner_clear_dependency_absent=$false} },
    @{ name='short_truth_table'; action={param($c) $c.rob_owner_contract.banks[0].checked_vectors=1535} },
    @{ name='wrong_wb_mapping'; action={param($c) $c.rob_owner_contract.banks[3].source_port=3} },
    @{ name='missing_read_mask'; action={param($c) $c.rob_owner_contract.local_read_checks[0].checked_vectors=0} },
    @{ name='overstated_proof'; action={param($c) $c.rob_owner_contract.full_sequential_equivalence_proven=$true} }
)) {
    $copy = $cpu | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    & $mutation.action $copy
    $failed = $false
    try { Assert-FpgaRobOwnerContract $copy $snapshot } catch {
        if ($_.Exception.Message -notlike 'ROB ADS *') { throw }
        $failed = $true
    }
    if (!$failed) { throw ('ROB contract accepted invalid fixture: '+$mutation.name) }
    $checks.Add($mutation.name + '_rejected')
}
$old = $snapshot | ConvertTo-Json -Depth 5 | ConvertFrom-Json
$old.release = 'V6.1'
Assert-FpgaRobOwnerContract ([pscustomobject]@{}) $old
$checks.Add('historical_v61_keeps_original_contract_scope')
# Opt-in is frozen by input hash, independent of marketing release numbers.
$current = $snapshot | ConvertTo-Json -Depth 8 | ConvertFrom-Json
$current.release = 'V2.1'
$current.inputs | Add-Member -NotePropertyName 'config/rob_result_contract.json' -NotePropertyValue ('7'*64)
$profiled = $cpu | ConvertTo-Json -Depth 8 | ConvertFrom-Json
$profiled.rob_owner_contract | Add-Member -NotePropertyName 'profile' -NotePropertyValue 'owner_valid_c1'
$profiled.rob_owner_contract | Add-Member -NotePropertyName 'profile_sha256' -NotePropertyValue ('7'*64)
Assert-FpgaRobOwnerContract $profiled $current
$checks.Add('v21_frozen_explicit_owner_valid_profile_accepted')
foreach ($mutation in @(
    @{name='missing_profile_proof'; action={param($c) $c.rob_owner_contract=$null}},
    @{name='wrong_profile'; action={param($c) $c.rob_owner_contract.profile='onehot_unproven'}},
    @{name='wrong_profile_hash'; action={param($c) $c.rob_owner_contract.profile_sha256='8'*64}},
    @{name='explicit_profile_cannot_skip_owner'; action={param($c) $c.rob_owner_contract.owner_ff=0}},
    @{name='explicit_profile_cannot_skip_reads'; action={param($c) $c.rob_owner_contract.local_read_checks=@()}}
)) {
    $copy=$profiled | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    & $mutation.action $copy
    $failed=$false
    try { Assert-FpgaRobOwnerContract $copy $current } catch {
        if ($_.Exception.Message -notlike 'ROB ADS *') { throw }; $failed=$true
    }
    if (!$failed) { throw ('ROB explicit profile accepted invalid fixture: '+$mutation.name) }
    $checks.Add($mutation.name+'_rejected')
}
$result = [ordered]@{ status='PASS'; scope='SYNTHETIC_CONTRACT_NO_PDS_NO_HARDWARE'; count=$checks.Count; checks=@($checks.ToArray()) }
if ($ReportPath) { $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8 }
Write-Output "ROB_ADS_CONTRACT_TESTS_PASS checks=$($checks.Count)"
