param([string]$ReportPath='')
$ErrorActionPreference='Stop'
$promotedReportPath=$ReportPath
. (Join-Path $PSScriptRoot 'test_rob_ads_contract.ps1')
$current.inputs | Add-Member -NotePropertyName 'scripts/audit_rob_promoted_reads_ads.py' -NotePropertyValue ('9'*64)
$new=$profiled | ConvertTo-Json -Depth 12 | ConvertFrom-Json
$new.rob_owner_contract.profile='owner_valid_c1_promoted'
$new.rob_owner_contract.scope='MAPPED_ROB_C1_PROMOTED_READS_LIMITED'
$new.rob_owner_contract.local_read_checks=@()
$new.rob_owner_contract | Add-Member -NotePropertyName promoted_read_contract -NotePropertyValue ([pscustomobject]@{
 status='PROMOTED_EFFECTIVE_ROB_READS_COFACTORED_WB_OFF_PASS_NOT_SEQ_OR_STA';checker_sha256='9'*64
 consumer_connections_proved=$true;unbound_values_are_free=$true;all_output_cofactors_resolved=$true
 writeback_disabled=@('Rob.io_mduWb_valid','Rob.io_memFwd_valid','FuAlu0.exValid_Q','FuAlu1.exValid_Q')
 reads=@(0,2 | ForEach-Object {$port=$_;[pscustomobject]@{tag_lane=$port+2;bank_read_port=4-$port;consumer="Dispatch.io_robRdata_$port";producer="Rob.io_rdata_$port";checked_vectors=512;checked_data_bits=32;nonconstant_bits=32}})
 consumer_connections=@(0,2 | ForEach-Object {$port=$_;[pscustomobject]@{consumer_path='u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_dispatch';producer_path='u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob';consumer_port="io_robRdata_$port";producer_port="io_rdata_$port";bits=32}})
})
Assert-FpgaRobOwnerContract $new $current
$checks.Add('promoted_effective_consumer_profile_accepted')
foreach($mutation in @(
 @{name='promoted_missing_proof';action={param($c) $c.rob_owner_contract.promoted_read_contract=$null}},
 @{name='promoted_wrong_helper_hash';action={param($c) $c.rob_owner_contract.promoted_read_contract.checker_sha256='8'*64}},
 @{name='promoted_missing_owner';action={param($c) $c.rob_owner_contract.owner_ff=0}},
 @{name='promoted_missing_read_bindings';action={param($c) $c.rob_owner_contract.read_port_bindings=@()}},
 @{name='promoted_short_vectors';action={param($c) $c.rob_owner_contract.promoted_read_contract.reads[0].checked_vectors=511}},
 @{name='promoted_missing_data_bit';action={param($c) $c.rob_owner_contract.promoted_read_contract.reads[0].checked_data_bits=31}},
 @{name='promoted_wrong_consumer';action={param($c) $c.rob_owner_contract.promoted_read_contract.reads[0].consumer='synthetic_unknown'}},
 @{name='promoted_wrong_binding';action={param($c) $c.rob_owner_contract.promoted_read_contract.consumer_connections[0].consumer_port='io_robRdata_1'}},
 @{name='promoted_unproved_binding';action={param($c) $c.rob_owner_contract.promoted_read_contract.consumer_connections_proved=$false}},
 @{name='promoted_unknown_forced_zero';action={param($c) $c.rob_owner_contract.promoted_read_contract.unbound_values_are_free=$false}},
 @{name='promoted_unresolved_output';action={param($c) $c.rob_owner_contract.promoted_read_contract.all_output_cofactors_resolved=$false}},
 @{name='promoted_incomplete_wb_mask';action={param($c) $c.rob_owner_contract.promoted_read_contract.writeback_disabled=@()}},
 @{name='promoted_overstated_scope';action={param($c) $c.rob_owner_contract.full_sequential_equivalence_proven=$true}}
)){
 $copy=$new | ConvertTo-Json -Depth 14 | ConvertFrom-Json
 & $mutation.action $copy
 $failed=$false
 try{Assert-FpgaRobOwnerContract $copy $current}catch{if($_.Exception.Message -notlike 'ROB ADS *'){throw};$failed=$true}
 if(!$failed){throw ('ROB promoted profile accepted invalid fixture: '+$mutation.name)}
 $checks.Add($mutation.name+'_rejected')
}
$result=[ordered]@{status='PASS';scope='SYNTHETIC_CONTRACT_NO_PDS_NO_HARDWARE';count=$checks.Count;checks=@($checks.ToArray())}
if($promotedReportPath){[IO.File]::WriteAllText($promotedReportPath,($result|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "ROB_PROMOTED_CONTRACT_TESTS_PASS checks=$($checks.Count)"
