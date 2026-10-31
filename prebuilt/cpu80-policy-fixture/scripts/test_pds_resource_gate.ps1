param(
    [Parameter(Mandatory=$true)][string]$Report,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'build_fpga.ps1'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Cannot parse current FPGA build entry' }
$functions = @($ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -ceq 'Assert-FpgaSynthResources'
}, $true))
if ($functions.Count -ne 1) { throw 'Expected exactly one current ADS resource gate' }
Invoke-Expression $functions[0].Extent.Text
$reportPath = [IO.Path]::GetFullPath($Report)
$original = [IO.File]::ReadAllText($reportPath)
$originalHash = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant()
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('soc_resource_fixture_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$fixtureReport = Join-Path $fixture 'soc_top.snr'
function Replace-ResourceLine([string]$Body, [string]$Pattern, [string]$Replacement) {
    if ([regex]::Matches($Body, $Pattern).Count -ne 1) { throw 'Unknown ADS report shape' }
    return [regex]::Replace($Body, $Pattern, $Replacement)
}
try {
    $cases = @(
        @('actual_report', $original, ''),
        @('drm_above_budget', (Replace-ResourceLine $original '(?m)^Total DRM = .*$' 'Total DRM = 141.0 of 155 (90.97%)'), 'ADS resource budget exceeded: DRM'),
        @('lut_above_capacity', (Replace-ResourceLine $original '(?m)^Total LUTs: .*$' 'Total LUTs: 66601 of 66600 (100.01%)'), 'ADS resource budget exceeded: LUT'),
        @('lutram_above_capacity', (Replace-ResourceLine $original '(?m)^\s*LUTs as dram: .*$' 'LUTs as dram: 19901 of 19900 (100.01%)'), 'ADS resource budget exceeded: LUTRAM'),
        @('ff_above_capacity', (Replace-ResourceLine $original '(?m)^Total Registers: .*$' 'Total Registers: 133201 of 133200 (100.01%)'), 'ADS resource budget exceeded: FF'),
        @('missing_count', (Replace-ResourceLine $original '(?m)^Total DRM = .*$' ''), 'ADS resource count missing or ambiguous: DRM'),
        @('latch_present', (Replace-ResourceLine $original '(?m)^Total Latches: .*$' 'Total Latches: 1'), 'ADS resource gate requires exactly one zero-latch summary')
    )
    $results = @()
    foreach ($case in $cases) {
        [IO.File]::WriteAllText($fixtureReport, $case[1], [Text.UTF8Encoding]::new($false))
        $failure = ''
        try { $null = Assert-FpgaSynthResources $fixtureReport ([datetime]::MinValue) 6>$null }
        catch { $failure = $_.Exception.Message }
        if (($case[2] -eq '' -and $failure) -or
            ($case[2] -ne '' -and !$failure.StartsWith($case[2], [StringComparison]::Ordinal))) {
            throw "Resource gate case $($case[0]) returned unexpected failure: $failure"
        }
        $results += [ordered]@{ case=$case[0]; status='PASS'; expected=$(if ($case[2]) { 'REJECT' } else { 'ACCEPT' }); diagnostic=$failure }
    }
    if ((Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $originalHash) {
        throw 'Input ADS report changed during fixture'
    }
    $result = [ordered]@{
        schema = 2; status = 'PASS'; scope = 'Actual current PowerShell resource gate on a supplied ADS report plus synthetic faults; no PDS rerun'
        report_sha256 = $originalHash
        gate_source_sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        cases = $results
    }
    $target = [IO.Path]::GetFullPath($Output)
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    [IO.File]::WriteAllText($target, ($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    Write-Output "PDS_RESOURCE_GATE_FIXTURES_PASS cases=$($results.Count) actual_build_function=true"
} finally {
    if ((Test-Path -LiteralPath $fixture -PathType Container) -and
        $fixture.StartsWith(([IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'),
            [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}
