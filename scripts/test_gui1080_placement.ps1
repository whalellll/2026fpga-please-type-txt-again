param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$testRoot=Join-Path 'G:/fpga/performance_soc_voice_hw/build/cpu80-gui1080-accept-20261023' ('placement-fixture-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $testRoot 'pds') -Force | Out-Null
$path=Join-Path $testRoot 'pds/gui1080_tage.pcf'
$line='def_inst_site {u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k} DRM_256_30 DRM0'
$stdout='Executing : '+$line+" successfully`nGUI1080_STRICT_PLACEMENT_REAPPLIED_AFTER_MAP`n"
$checks=[Collections.Generic.List[string]]::new()
function Reject([string]$Name,[scriptblock]$Action){
 $failed=$false
 try{& $Action}catch{$failed=$true}
 if(!$failed){throw "Invalid placement accepted: $Name"}
 $checks.Add($Name)
}
try{
 [IO.File]::WriteAllText($path,$line)
 Assert-FpgaGui1080PlacementNative $testRoot $stdout $line ($line+' -no_check')
 $checks.Add('exact_native_fixture_pass')
 foreach($bad in @(($line+' -no_check'),($line+"`n"+$line),$line.Replace('DRM_256_30','DRM_40_246'),$line.Replace('DRM0','DRM1'),$line.Replace('Memory_1','Memory'))){
  [IO.File]::WriteAllText($path,$bad)
  Reject 'invalid_input_rejected' {Assert-FpgaGui1080PlacementInput $testRoot}
 }
 [IO.File]::WriteAllText($path,$line)
 foreach($bad in @('', ($stdout+$stdout),$stdout.Replace(' successfully',' failed'),$stdout.Replace('GUI1080_STRICT_PLACEMENT_REAPPLIED_AFTER_MAP',''))){
  Reject 'missing_duplicate_failed_execution_rejected' {Assert-FpgaGui1080PlacementNative $testRoot $bad $line $line}
 }
 foreach($bad in @('',($line+"`n"+$line),($line+' -no_check'))){
  Reject 'missing_duplicate_nocheck_mapped_input_rejected' {Assert-FpgaGui1080PlacementNative $testRoot $stdout $bad $line}
 }
 foreach($bad in @('',($line+"`n"+$line),$line.Replace('DRM_256_30','DRM_256_90'),$line.Replace('DRM0','DRM1'),$line.Replace('Memory_1','Memory'))){
  Reject 'missing_duplicate_wrong_actual_location_rejected' {Assert-FpgaGui1080PlacementNative $testRoot $stdout $line $bad}
 }
 $record=[ordered]@{status='GUI1080_STRICT_PLACEMENT_FIXTURE_17_REJECTIONS_PASS_NOT_NATIVE_STA_OR_BOARD';checks=@($checks);count=$checks.Count}
 if($checks.Count -ne 18){throw "Unexpected placement fixture coverage: $($checks.Count)"}
 $nets=@(
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [0]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [1]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[1].ddrphy_data_slice/adj_wrdqs [0]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [61]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [10]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/adj_wrdata_mask [7]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/frontend/ftqAlloc [3]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_mdu_io_wbData [0]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rs_alu1/issueUsesFast',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_alu0_io_wbData [20]',
 'u_video/s4_fx [1]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_mdu_io_wbValid',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_rs_alu0_io_issueRobid [1]',
 'u_eth/tx_pos [5]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [41]',
 'I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/adj_wrdq [58]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/memShadowRobid [4]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_lsu/stqPa_1 [26]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/frontend/pdInsts_2 [28]',
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rs_alu1/N1294 [0]')
 $lines=@($nets|ForEach-Object {'def_route -prior_net {'+$_+'}'})
 if(($lines -join "`n") -cne ((Get-FpgaDdrRouteLines) -join "`n")){throw 'Twenty independently specified route names differ'}
 $routePath=Join-Path $testRoot 'pds/ddr3_test.rcf'
 [IO.File]::WriteAllLines($routePath,$lines)
 $project='(_widget wgt_edit_route_cons (_attribute _click_to_run (_switch ON)) (_input (_file "ddr3_test.rcf" (_format rcf) (_timespec "2026-10-23T00:00:00"))))'
 $parse="Executing : add_constraint soc.fdc successfully.`nExecuting : add_constraint ddr3_test.rcf successfully."
 $routeLog=($lines|ForEach-Object {'Executing : '+$_+' successfully.'}) -join "`n"
 $netlist=($nets|ForEach-Object {$_+';'}) -join "`n"
 Assert-FpgaDdrRouteRegistration $testRoot $project $parse $routeLog $netlist
 $checks.Add('twenty_exact_native_route_fixture_pass')
 $simple='u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_mdu_io_wbValid'
 $braced='Executing : def_route -prior_net {'+$simple+'} successfully.'
 $bare='Executing : def_route -prior_net '+$simple+' successfully.'
 $normalized=$routeLog.Replace($braced,$bare)
 Assert-FpgaDdrRouteRegistration $testRoot $project $parse $normalized $netlist
 $checks.Add('native_simple_tcl_word_without_braces_pass')
 Reject 'mixed_spelling_duplicate_native_execution_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse ($normalized+"`n"+$braced) $netlist}
 Reject 'failed_unbraced_native_execution_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse ($normalized.Replace($bare,$bare.Replace('successfully.','failed.'))) $netlist}
 Reject 'different_unbraced_net_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse ($normalized.Replace($simple,$simple+'_other')) $netlist}
 foreach($target in $nets){
  $success='Executing : def_route -prior_net {'+$target+'} successfully.'
  Reject 'route_missing_actual_execution_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse ($routeLog.Replace($success,'')) $netlist}
  Reject 'route_duplicate_execution_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse ($routeLog+"`n"+$success) $netlist}
  Reject 'route_missing_actual_net_rejected' {Assert-FpgaDdrRouteRegistration $testRoot $project $parse $routeLog ($netlist.Replace($target+';',''))}
 }
 foreach($bad in @(($lines[0..10] -join "`n"),(($lines+$lines[0]) -join "`n"))){
  [IO.File]::WriteAllText($routePath,$bad)
  Reject 'old_or_duplicate_route_input_rejected' {Assert-FpgaDdrRouteInput $testRoot $project}
 }
 $record['route_checks']=@($checks | Select-Object -Skip 18)
 $record['count']=$checks.Count
 if($checks.Count -ne 85){throw "Unexpected combined placement/route coverage: $($checks.Count)"}
 if($ReportPath){[IO.File]::WriteAllText($ReportPath,($record|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))}
 Write-Output ($record|ConvertTo-Json -Compress)
}finally{
 # Fixture is deliberately left with its input for review; no project/build deletion.
}
