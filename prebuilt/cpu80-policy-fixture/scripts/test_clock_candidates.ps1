param(
    [string]$DtcPath = 'D:\LJL\WORK\msys64\usr\bin\dtc.exe',
    [string]$ReportPath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'test_fpga_stage_fixture.ps1')
. (Join-Path $PSScriptRoot 'coremark_release_checks.ps1')
$root = Split-Path -Parent $PSScriptRoot
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$fixture = Join-Path $tempBase ('soc_clock_fixture_' + [guid]::NewGuid().ToString('N'))
$checks = [Collections.Generic.List[string]]::new()
function Write-Text([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}
function Reject([string]$Name, [scriptblock]$Action, [string]$Message) {
    try { & $Action | Out-Null } catch {
        if ($_.Exception.Message -notlike $Message) { throw "Unexpected ${Name}: $($_.Exception.Message)" }
        $checks.Add($Name)
        return
    }
    throw "Negative fixture was accepted: $Name"
}
try {
    $paths = @('VERSION','config/clocks.json','config/timing_scope_baseline.json','rtl/cpu/CoreTop.sv','rtl/video/pll_video.v','rtl/video/pll_cpu.v','rtl/soc/soc_top.v',
        'pds/soc.fdc','sw/bootloader/soc.h','sw/coremark/core_portme.h',
        'linux/soc.dts','linux/boot/soc.dtb','sim/tb_cpu_integration.sv',
        'scripts/coremark_fixed_bootloader.ps1','scripts/run_coremark_production_sim.ps1',
        'scripts/measure_coremark.ps1')
    foreach ($relative in $paths) {
        $destination = Join-Path $fixture $relative
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
        Copy-Item -LiteralPath (Join-Path $root $relative) -Destination $destination
    }
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'docs/validation/frequency-search') -Force
    $legacyEvidence = Join-Path $fixture 'docs/validation/frequency-search/divisor-14.inputs.json'
    Write-Text $legacyEvidence 'immutable historical fixture bytes'
    $legacyHash = (Get-FileHash -LiteralPath $legacyEvidence).Hash
    $fdcPath = Join-Path $fixture 'pds/soc.fdc'
    $expected = @{
        18 = @(49500000,'20.202020',16); 17 = @(52411765,'19.079686',16)
        16 = @(55687500,'17.957351',16); 15 = @(59400000,'16.835017',16)
        14 = @(63642857,'15.712682',14.912); 13 = @(68538462,'14.590348',13.790)
        12 = @(74250000,'13.468013',12.668)
    }
    $originalHashes = @{}
    foreach ($relative in $paths) { $originalHashes[$relative] = (Get-FileHash (Join-Path $fixture $relative)).Hash }
    & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 14 -DtcPath $DtcPath | Out-Null
    foreach ($relative in $paths) {
        if ((Get-FileHash (Join-Path $fixture $relative)).Hash -cne $originalHashes[$relative]) {
            throw "Dry-run changed fixture input: $relative"
        }
    }
    $checks.Add('dry_run_preserves_all_input_bytes')
    foreach ($divisor in @(14,13,12,18,17,16,15)) {
        $current = Get-Content (Join-Path $fixture 'config/clocks.json') -Raw | ConvertFrom-Json
        if ($current.cpu_divisor -ne $divisor) {
            & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor $divisor -DtcPath $DtcPath -Apply | Out-Null
        }
        & (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture | Out-Null
        $null=Assert-CoremarkPllClock $fixture $expected[$divisor][0]
        $clock = Get-Content (Join-Path $fixture 'config/clocks.json') -Raw | ConvertFrom-Json
        $fdc = [IO.File]::ReadAllText($fdcPath)
        if ($clock.cpu_hz -ne $expected[$divisor][0] -or
            !$fdc.Contains('-name {cpu_clk} -period {' + $expected[$divisor][1] + '}') -or
            (Assert-SocCdcBounds $fdc) -ne $expected[$divisor][2]) { throw "Wrong div$divisor derivation" }
        $reports = New-TestFpgaMaxSkewReports $fdcPath
        $xml = Join-Path $fixture 'skew.xml'; $rtr = Join-Path $fixture 'skew.rtr'
        Write-Text $xml $reports.xml; Write-Text $rtr $reports.rtr
        $accepted = Assert-FpgaMaxSkewReport $xml $rtr $fdcPath
        if ($accepted.groups -ne 10 -or $accepted.rows -ne 20) { throw 'Incomplete two-corner Gray coverage' }
        $checks.Add("div${divisor}_pll_dtb_software_fdc_and_two_corner_skew")
        if ($divisor -eq 14) {
            $newXml = $reports.xml
            Write-Text $xml ($newXml.Replace('14.912','16.000').Replace('13.912','15.000'))
            Reject 'old_16ns_report_rejected_for_div14' { Assert-FpgaMaxSkewReport $xml $rtr $fdcPath } '*violation or inconsistent slack*'
            Write-Text $xml $newXml
            Write-Text $fdcPath ($fdc.Replace('14.912','16.0'))
            Reject 'unsafe_div14_16ns_bounds_rejected' { & (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture } '*CDC bound differs*'
            Write-Text $fdcPath $fdc
        }
    }
    & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 12 -CpuClockSource dedicated850p5 -DtcPath $DtcPath -Apply | Out-Null
    $dedicated=Get-Content (Join-Path $fixture 'config/clocks.json') -Raw|ConvertFrom-Json
    if($dedicated.cpu_hz -ne 70875000 -or (Assert-SocCdcBounds ([IO.File]::ReadAllText($fdcPath))) -ne [decimal]13.309){throw 'Dedicated profile derivation failed'}
    $null=Assert-CoremarkPllClock $fixture 70875000
    $checks.Add('dedicated_pll_dtb_fdc_software_70875000')
    $dedicatedFdc=[IO.File]::ReadAllText($fdcPath)
    Write-Text $fdcPath ($dedicatedFdc.Replace('g_dedicated_cpu.u_cpu_pll/clkout3','u_video_pll/clkout3'))
    Reject 'old_fdc_cpu_clock_output_rejected' {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*FDC CPU clock target*'
    Write-Text $fdcPath $dedicatedFdc
    $scopePath=Join-Path $fixture 'config/timing_scope_baseline.json'
    $scopeText=[IO.File]::ReadAllText($scopePath)
    Write-Text $scopePath ($scopeText.Replace('g_dedicated_cpu.u_cpu_pll/u_gpll/gpll_inst/CLKOUT3','u_video_pll/u_gpll/gpll_inst/CLKOUT3'))
    Reject 'old_clock_scope_cpu_target_rejected' {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*STA scope CPU target*'
    Write-Text $scopePath $scopeText
    $cpuPllPath=Join-Path $fixture 'rtl/video/pll_cpu.v'
    $cpuPll=[IO.File]::ReadAllText($cpuPllPath)
    foreach($mutation in @(@('STATIC_RATIOF\s*=\s*CPU_CLOCK_MODE == 2 \? 25\.0 : 15\.75','STATIC_RATIOF = 16.5'),@('\.CLKOUT3\s*\(clkout3\s*\)', '.CLKOUT3 (wrong_clk)'),@('\.STATIC_RATIOF\s*\(STATIC_RATIOF\s*\)', '.STATIC_RATIOF (16.5)'))){
        if([regex]::Matches($cpuPll,$mutation[0]).Count -ne 1){throw 'Dedicated mutation anchor missing'}
        Write-Text $cpuPllPath ([regex]::Replace($cpuPll,$mutation[0],$mutation[1]))
        Reject ('dedicated_primitive_'+$checks.Count) {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*Dedicated CPU GPLL*'
        Write-Text $cpuPllPath $cpuPll
    }
    & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 12 -CpuClockSource video891 -DtcPath $DtcPath -Apply | Out-Null
    $checks.Add('same_divisor_switches_actual_pll_source')
    $before75Exceptions=@([IO.File]::ReadAllText($fdcPath) -split '\r?\n' | Where-Object {$_ -match '^set_(false_path|clock_groups|multicycle_path|clock_uncertainty) '})
    & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 9 -CpuClockSource dedicated675 -DtcPath $DtcPath -Apply | Out-Null
    $null=Assert-CoremarkPllClock $fixture 75000000
    $checks.Add('cpu75_exact_pll_dtb_fdc_software')
    $tightFdc75=[IO.File]::ReadAllText($fdcPath)
    if($tightFdc75 -notmatch 'create_clock -name \{cpu_clk\} -period \{13\.320000\}' -or (Assert-SocCdcBounds $tightFdc75) -ne [decimal]12.520){throw 'CPU75 tighter STA/CDC contract missing'}
    $after75Exceptions=@($tightFdc75 -split '\r?\n' | Where-Object {$_ -match '^set_(false_path|clock_groups|multicycle_path|clock_uncertainty) '})
    if(($before75Exceptions -join "`n") -cne ($after75Exceptions -join "`n")){throw 'CPU75 timing target changed timing exceptions'}
    $checks.Add('cpu75_tighter_sta_cdc_without_new_exceptions')
    if($tightFdc75 -notmatch 'create_clock -name \{sys_clk\} -period \{20\.202000\}'){throw 'CPU75 SYS period must use the explicit complete 1ps literal'}
    $checks.Add('cpu75_full_precision_sys_period_grid')
    Write-Text $fdcPath ($tightFdc75.Replace('20.202000','20.202020'))
    Reject 'cpu75_mixed_precision_sys_period_rejected' {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*reviewed timing target*'
    Write-Text $fdcPath $tightFdc75
    Write-Text $fdcPath ($tightFdc75.Replace('13.320000','13.333333'))
    Reject 'cpu75_old_unexpandable_period_rejected' {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*reviewed timing target*'
    Write-Text $fdcPath $tightFdc75
    Write-Text $fdcPath ($tightFdc75.Replace(' 12.52',' 12.533'))
    Reject 'cpu75_looser_cdc_bound_rejected' {& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture} '*CDC bound differs*'
    Write-Text $fdcPath $tightFdc75
    & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 12 -CpuClockSource video891 -DtcPath $DtcPath -Apply | Out-Null
    $evidenceDirectory = Join-Path $fixture 'docs/validation/frequency-search/candidates'
    foreach ($repeatDivisor in @(14,15,14)) {
        $preserved = @{}
        foreach ($file in Get-ChildItem -LiteralPath $evidenceDirectory -Recurse -File) {
            $preserved[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName).Hash
        }
        & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor $repeatDivisor -DtcPath $DtcPath -Apply | Out-Null
        foreach ($path in $preserved.Keys) {
            if ((Get-FileHash -LiteralPath $path).Hash -cne $preserved[$path]) { throw 'Repeat Apply overwrote prior candidate evidence' }
        }
        if (@(Get-ChildItem -LiteralPath $evidenceDirectory -Recurse -File).Count -ne $preserved.Count + 1) {
            throw 'Repeat Apply did not create exactly one new candidate record'
        }
    }
    if ((Get-FileHash -LiteralPath $legacyEvidence).Hash -cne $legacyHash) { throw 'Legacy frequency evidence changed' }
    $checks.Add('repeated_divisor_apply_preserves_every_previous_record')
    $checks.Add('legacy_divisor_evidence_remains_byte_identical')
    $newPath = 'docs/validation/frequency-search/candidates/V6.5/div14-20261008T1400000000000Z-' + ('a'*32) + '.inputs.json'
    if ((Get-SocCandidateEvidenceRelative 14 $newPath) -cne $newPath -or
        (Get-SocCandidateEvidenceRelative 14 '') -cne 'docs/validation/frequency-search/divisor-14.inputs.json') {
        throw 'Archive candidate path identity changed'
    }
    $checks.Add('explicit_unique_and_historical_candidate_paths_accepted')
    Reject 'wrong_divisor_candidate_path_rejected' { Get-SocCandidateEvidenceRelative 15 $newPath } '*Invalid or mismatched*'
    Reject 'candidate_path_traversal_rejected' { Get-SocCandidateEvidenceRelative 14 ($newPath.Replace('candidates/', 'candidates/../')) } '*Invalid or mismatched*'
    $beforeCount = @(Get-ChildItem -LiteralPath $evidenceDirectory -Recurse -File).Count
    Reject 'same_current_divisor_apply_rejected' {
        & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 14 -DtcPath $DtcPath -Apply
    } '*Refusing to apply the current divisor*'
    if (@(Get-ChildItem -LiteralPath $evidenceDirectory -Recurse -File).Count -ne $beforeCount) { throw 'Rejected Apply created evidence' }
    $pllPath = Join-Path $fixture 'rtl/video/pll_video.v'
    $pll = [IO.File]::ReadAllText($pllPath)
    Write-Text $pllPath ($pll.Replace('STATIC_RATIOF    = 16.5','STATIC_RATIOF    = 17.0'))
    Reject 'wrong_pll_feedback_rejected' { & (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture } '*PLL feedback divider*'
    Write-Text $pllPath $pll
    $fdc = [IO.File]::ReadAllText($fdcPath)
    Write-Text $fdcPath ([regex]::Replace($fdc, '(?m)^set_max_skew[^\r\n]+\r?\n', '', 1))
    Reject 'missing_gray_bound_rejected' { & (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $fixture } '*exactly nineteen*'
    Write-Text $fdcPath $fdc
    Reject 'outside_reviewed_window_rejected' { & (Join-Path $PSScriptRoot 'set_clock_candidate.ps1') -Root $fixture -Divisor 11 -DtcPath $DtcPath } '*11*ValidateSet*'
    $report = [ordered]@{ schema = 1; status = 'PASS'; kind = 'isolated-clock-policy-tests-not-hardware-evidence'; checks = @($checks) }
    if ($ReportPath) { Write-Text ([IO.Path]::GetFullPath($ReportPath)) (($report | ConvertTo-Json -Depth 5) + "`n") }
    Write-Output "SOC_CLOCK_CANDIDATE_TEST_PASS checks=$($checks.Count)"
} finally {
    if (Test-Path -LiteralPath $fixture) {
        $resolved = [IO.Path]::GetFullPath($fixture)
        $nodes = @(Get-Item -LiteralPath $resolved) + @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
        if (!$resolved.StartsWith($tempBase + '\soc_clock_fixture_', [StringComparison]::OrdinalIgnoreCase) -or
            @($nodes | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
            throw 'Refusing cleanup of an unsafe clock fixture path'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
