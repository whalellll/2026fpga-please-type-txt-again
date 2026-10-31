param([string]$Root=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$flow=[IO.File]::ReadAllText((Join-Path $Root 'pds/soc_post_synth.tcl'))
$gui=[IO.File]::ReadAllText((Join-Path $Root 'pds/soc_gui.pds'))
$expected='pnr -plc_decongestion 4 -gplace_seed 3 -optimize_multi_corner_timing -fix_hold_violation -mode performance -fix_hold_violation_threshold 200 -fix_hold_violation_iterations 12'
if (@($flow -split "`n"|Where-Object {$_.Trim() -ceq $expected}).Count -ne 1){throw 'CPU75 hold-repair candidate must retain the original PnR options and request exactly 12 iterations'}
if (!$gui.Contains('(_option fix_hold_violation_iterations (_integer 12))')){throw 'GUI must request the same 12 hold-repair iterations'}
if (@([regex]::Matches($flow,'(?m)^pnr\b')).Count -ne 1){throw 'One full PnR action required'}
Write-Output 'CPU75_HOLD12_POLICY_PASS no_PDS_or_hardware_run=true'
