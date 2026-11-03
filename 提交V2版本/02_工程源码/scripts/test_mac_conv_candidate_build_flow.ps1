param([switch]$InjectNativeError)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$trial = Join-Path $root ('build\vision\build_flow_test_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $trial | Out-Null
$fake = Join-Path $trial 'fake_pds.ps1'
@'
param([string]$file, [string]$project_name)
$ErrorActionPreference = 'Stop'
Add-Content calls.txt $file
if (!$project_name -or $project_name -eq [IO.Path]::GetFileNameWithoutExtension($file)) { exit 14 }
# Native PDS exports impl.tcl even with a different -project_name.
if ($file -eq 'impl.tcl') { exit 15 }
$script = Get-Content -LiteralPath $file -Raw
if ($file -eq 'impl_map.tcl') {
    if ($script -match '(?m)^pnr\b' -or $script -match '\[open') { exit 11 }
    New-Item -ItemType Directory device_map -Force | Out-Null
    '# native defaults' | Set-Content device_map/soc_v2_top.pcf
    @"
| APM | 195 | 200 |
| FF | 28932 | 100000 |
| LUT | 34308 | 100000 |
| DRM | 150 | 155 |
"@ | Set-Content device_map/run.log
} else {
    if ($script -notmatch '(?m)^set placement_out \[open \{device_map/soc_v2_top.pcf\} a\]') { exit 12 }
    $pcf = Get-Content device_map/soc_v2_top.pcf -Raw
    # The real tool executes these queued commands after its remapping action.
    Add-Content device_map/soc_v2_top.pcf (Get-Content placement_extra.pcf -Raw)
    $pcf = Get-Content device_map/soc_v2_top.pcf -Raw
    if ($pcf -notmatch '# native defaults' -or $pcf -notmatch 'def_inst_site') { exit 13 }
    New-Item -ItemType Directory generate_bitstream,report_timing,place_route -Force | Out-Null
    'candidate' | Set-Content generate_bitstream/soc_v2_top.sbit
    $lines = Get-Content placement_extra.pcf | Where-Object { $_ -match '^def_inst_site ' }
    $lines | ForEach-Object { "Executing : $_ successfully" } | Set-Content place_route/run.log
    "Setup Summary(Slow Corner):`nclk clk 0.532 0.000 1 1`nHold Summary(Slow Corner):`nDesign Summary : All Constraints Met." | Set-Content report_timing/soc_v2_top.rtr
    if (Test-Path native_error.flag) { Write-Output 'E: injected native failure with exit zero' }
}
exit 0
'@ | Set-Content -LiteralPath $fake -Encoding Ascii
# The nested resource literal uses a double-quoted here-string in the fake.
$out = Join-Path $trial 'out'
New-Item -ItemType Directory $out | Out-Null
if ($InjectNativeError) { New-Item -ItemType File (Join-Path $out 'native_error.flag') | Out-Null }
$caught = $false
try {
    & (Join-Path $PSScriptRoot 'build_mac_conv_stage2_soc_candidate.ps1') -PdsShell $fake -OutputDir $out -ExtraPlacementPcf pds/yolo_post_banked_ddr.pcf
} catch {
    $caught = $true
    if (!$InjectNativeError) { throw }
    if ($_.Exception.Message -notmatch 'native error') { throw }
}
if ($InjectNativeError -and !$caught) { throw 'Native error with exit zero was accepted' }
$calls = @(Get-Content (Join-Path $out 'calls.txt'))
if ($calls.Count -ne 2 -or $calls[0] -ne 'impl_map.tcl' -or $calls[1] -ne 'flow_input.tcl') {
    throw "Expected map, append PCF, implementation; got $calls"
}
Write-Output "MAC_CONV_CANDIDATE_BUILD_FLOW_PASS native_error=$InjectNativeError calls=$($calls.Count) evidence=$trial"
