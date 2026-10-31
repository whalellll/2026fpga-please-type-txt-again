param([string]$ReportPath = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$root = Split-Path -Parent $PSScriptRoot
# Use a preserved matching report/FDC pair; the live candidate clock can differ.
$baseline = Join-Path $root 'docs/validation/frequency-search/div15-PASS-6e934e9f84094159bff9a8870e260e8e/raw'
$xml = Join-Path $baseline 'artifacts/final_timing_xml.xml'
$fdc = Join-Path $baseline 'pds/soc.fdc'
$policy = Join-Path $root 'config/timing_scope_baseline.json'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('soc_sta_scope_' + [guid]::NewGuid().ToString('N') + '.xml')
$tempFdc = $temp + '.fdc'
$checks = [Collections.Generic.List[string]]::new()
function Reject-Scope([string]$Name, [scriptblock]$Mutation, [string]$Message) {
    [xml]$doc = [IO.File]::ReadAllText($xml)
    & $Mutation $doc
    $doc.Save($temp)
    try { $null = Assert-FpgaTimingScope $temp $fdc $policy } catch {
        if ($_.Exception.Message -notlike $Message) { throw "Unexpected ${Name}: $($_.Exception.Message)" }
        $checks.Add($Name); return
    }
    throw "Unsafe timing fixture accepted: $Name"
}
try {
    $accepted = Assert-FpgaTimingScope $xml $fdc $policy
    $checks.Add('native_baseline_full_scope_pass_with_disclosed_io_gaps')
    Reject-Scope 'missing_clock_rejected' {
        param($doc)
        $row = $doc.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]//row[data[1]="cpu_clk"]')
        $null = $row.ParentNode.RemoveChild($row)
    } '*eighteen reviewed clocks*'
    Reject-Scope 'wrong_cpu_period_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]//row[data[1]="cpu_clk"]/data[3]').InnerText = '17.0000'
    } '*clock definition differs: cpu_clk*'
    Reject-Scope 'new_unclocked_internal_endpoint_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="check_timing_summary"]/row[data[1]="no_clock"]/data[2]').InnerText = '1'
    } '*check_timing gap changed: no_clock*'
    Reject-Scope 'missing_check_timing_count_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="check_timing_summary"]/row[data[1]="no_clock"]/data[2]').InnerText = ''
    } '*Invalid check_timing count: no_clock*'
    Reject-Scope 'changed_unconstrained_port_identity_rejected' {
        param($doc)
        $node = $doc.SelectSingleNode('/tables/table[@id="report_timing_messages"]/row/data[starts-with(text(),"Timing-4086:")]')
        $node.InnerText = "Timing-4086: Port 'new_port' is not constrained, it is treated as combinational input."
    } '*Unconstrained port set differs*'
    Reject-Scope 'new_internal_unconstrained_warning_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="report_timing_messages"]/row[1]/data').InnerText = 'Timing-9999: internal register has no constraint'
    } '*Unreviewed native STA warning*'
    Reject-Scope 'negative_fast_hold_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="report_timing_fast_hold"]/row[1]/data[3]').InnerText = '-0.001'
    } '*fast/hold has a violation*'
    Reject-Scope 'missing_slow_setup_domain_rejected' {
        param($doc)
        $table = $doc.SelectSingleNode('/tables/table[@id="report_timing_slow_setup"]')
        $null = $table.RemoveChild($table.SelectSingleNode('./row[1]'))
    } '*slow/setup clock-pair coverage changed*'
    Reject-Scope 'wrong_native_max_delay_rejected' {
        param($doc)
        $doc.SelectSingleNode('/tables/table[@id="exception_report_slow_set_max_delay_setup"]/row[1]/data[15]').InnerText = '99.000'
    } '*Native max-delay bound differs*'
    [IO.File]::WriteAllText($tempFdc, [IO.File]::ReadAllText($fdc) + "`nset_false_path -from [get_clocks {cpu_clk}] -to [get_clocks {sys_clk}]`n", [Text.UTF8Encoding]::new($false))
    try { $null = Assert-FpgaTimingScope $xml $tempFdc $policy; throw 'Unsafe timing exception accepted' } catch {
        if ($_.Exception.Message -notlike '*Timing exceptions differ*') { throw }
        $checks.Add('added_false_path_rejected')
    }
    $result = [ordered]@{ schema=1; kind='native-report-mutation-tests-not-new-hardware-evidence'; status='PASS'; checks=@($checks); baseline_scope=$accepted }
    if ($ReportPath) { [IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath), ($result | ConvertTo-Json -Depth 6) + "`n", [Text.UTF8Encoding]::new($false)) }
    Write-Output "TIMING_SCOPE_TEST_PASS checks=$($checks.Count)"
} finally {
    foreach ($path in @($temp,$tempFdc)) { if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force } }
}
