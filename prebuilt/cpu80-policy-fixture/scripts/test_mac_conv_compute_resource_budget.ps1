param(
    [Parameter(Mandatory = $true)][string]$MapRunLog,
    [int]$MaxApm = 195,
    [int]$MaxLut = 37500
)

$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $MapRunLog -PathType Leaf)) {
    throw "PDS device map report missing: $MapRunLog"
}
$report = Get-Content -LiteralPath $MapRunLog -Raw
$counts = @{}
foreach ($name in @('APM', 'LUT')) {
    $match = [regex]::Match($report,
        '(?m)^\|\s*' + $name + '\s*\|\s*(\d+)\s*\|')
    if (!$match.Success) { throw "PDS $name resource count missing" }
    $counts[$name] = [int]$match.Groups[1].Value
}
if ($counts.APM -gt $MaxApm -or $counts.LUT -gt $MaxLut) {
    throw "MAC compute resource budget exceeded: APM=$($counts.APM)/$MaxApm LUT=$($counts.LUT)/$MaxLut"
}
Write-Output "MAC_CONV_COMPUTE_RESOURCE_PASS apm=$($counts.APM) lut=$($counts.LUT)"
