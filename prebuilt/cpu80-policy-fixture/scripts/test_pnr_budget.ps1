$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_pnr_budget.ps1')
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('pnr-budget-fixture-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$ledgerPath = Join-Path $fixture 'budget.json'
$snapshotPath = Join-Path $fixture 'snapshot.json'
[IO.File]::WriteAllText($snapshotPath, '{"synthetic_fixture":true}')
$now = [DateTimeOffset]::UtcNow
$ledger = [ordered]@{
    schema = 1; task_started = $now.ToString('o'); deadline = $now.AddHours(24).ToString('o')
    maximum_full_pnr_starts = 6; attempts = @(); status = 'SYNTHETIC_FIXTURE_ONLY'
}
[IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 5))
function Expect-Rejection([string]$Purpose, [string]$Id, [string]$Pattern) {
    $before = (Get-FileHash -LiteralPath $ledgerPath).Hash
    $failure = ''
    try { Register-PnrAttempt $ledgerPath $Id $Purpose $snapshotPath | Out-Null } catch { $failure = $_.Exception.Message }
    if ($failure -notmatch $Pattern) { throw "Expected $Pattern, got $failure" }
    if ((Get-FileHash -LiteralPath $ledgerPath).Hash -ne $before) { throw 'Rejected launch changed budget' }
}
foreach ($index in 1..4) { Register-PnrAttempt $ledgerPath "search$index" 'search' $snapshotPath | Out-Null }
Expect-Rejection 'search' 'fifth-search' 'reserved'
Expect-Rejection 'search' 'search1' 'duplicate'
Register-PnrAttempt $ledgerPath 'control' 'same_frequency' $snapshotPath | Out-Null
Expect-Rejection 'same_frequency' 'second-control' 'reserved'
Register-PnrAttempt $ledgerPath 'final' 'final' $snapshotPath | Out-Null
Expect-Rejection 'final' 'seventh' 'limit'
$saved = [IO.File]::ReadAllText($ledgerPath)
$authorized = $saved | ConvertFrom-Json
$authorized | Add-Member user_override ([pscustomobject]@{active=$true;source='direct user message';authorization='ignore_pnr_budget';instruction='SYNTHETIC IGNORE PNR BUDGET';scope='SYNTHETIC_FIXTURE_ONLY'})
$authorized.deadline = $now.AddDays(-1).ToString('o')
[IO.File]::WriteAllText($ledgerPath,($authorized|ConvertTo-Json -Depth 8))
Register-PnrAttempt $ledgerPath 'authorized-seven' 'search' $snapshotPath | Out-Null
Register-PnrAttempt $ledgerPath 'authorized-eight' 'final' $snapshotPath | Out-Null
Expect-Rejection 'final' 'authorized-eight' 'duplicate'
$bad=[IO.File]::ReadAllText($ledgerPath)|ConvertFrom-Json
$bad.user_override.source='skill or historical approval'
[IO.File]::WriteAllText($ledgerPath,($bad|ConvertTo-Json -Depth 8))
Expect-Rejection 'final' 'not-authorized' 'authorization'
[IO.File]::WriteAllText($ledgerPath,$saved)
$ledger.attempts = @()
$ledger.deadline = $now.AddSeconds(-1).ToString('o')
[IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 5))
Expect-Rejection 'search' 'late' 'deadline'
$ledger.deadline = $now.AddHours(25).ToString('o')
[IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 5))
Expect-Rejection 'search' 'extended' 'policy'
Write-Output "PNR_BUDGET_TEST_PASS ordinary_launches=6 authorized_override_launches=2 rejections=8 NO_PDS fixture=$fixture"
