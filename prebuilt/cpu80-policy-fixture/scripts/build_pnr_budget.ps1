# Campaign accounting is outside the frozen FPGA inputs. A recorded launch
# consumes an attempt even if native PDS fails, times out, or is cancelled.
function Resolve-PnrCampaignBudget {
    param([string]$Root, [string]$Requested)
    if (!$Requested -and [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim() -ceq '6.5') {
        $Requested = Join-Path $Root 'docs/validation/v6_5-development-20261008/search-budget.json'
    }
    if (!$Requested) { return '' }
    $full = [IO.Path]::GetFullPath($Requested)
    if (!(Test-Path -LiteralPath $full -PathType Leaf)) { throw 'Missing campaign budget ledger' }
    $cursor = $full
    while ($cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked PnR ledger path' }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}

function Test-PnrUserBudgetOverride($Ledger) {
    if (!$Ledger.user_override -or !$Ledger.user_override.active) { return $false }
    if ($Ledger.user_override.source -cne 'direct user message' -or
        $Ledger.user_override.authorization -cne 'ignore_pnr_budget' -or
        [string]::IsNullOrWhiteSpace($Ledger.user_override.scope)) {
        throw 'Invalid PnR user authorization override'
    }
    return $true
}

function Get-PnrStageRemainingSeconds($Ledger) {
    if (Test-PnrUserBudgetOverride $Ledger) { return 86400 }
    return [int][Math]::Floor(([DateTimeOffset]::Parse($Ledger.deadline) - [DateTimeOffset]::UtcNow).TotalSeconds)
}

function Assert-PnrBudgetPolicy {
    param($Ledger, [string]$Purpose, [string]$RunId = '')
    if ($Purpose -cnotin @('search','same_frequency','final')) { throw 'Invalid PnR purpose' }
    $start = [DateTimeOffset]::Parse($Ledger.task_started)
    $deadline = [DateTimeOffset]::Parse($Ledger.deadline)
    $now = [DateTimeOffset]::UtcNow
    if (Test-PnrUserBudgetOverride $Ledger) {
        if ($Ledger.schema -ne 1 -or $start -gt $now -or
            ($RunId -and @($Ledger.attempts | Where-Object {$_.run_id -ceq $RunId}).Count)) {
            throw 'Invalid authorized PnR ledger or duplicate run ID'
        }
        # The direct user instruction cancels this campaign's count/time budget.
        # Native per-job timeouts and every correctness/STA/board gate remain.
        return $now.AddDays(1)
    }
    if ($Ledger.schema -ne 1 -or $Ledger.maximum_full_pnr_starts -ne 6 -or
        $start -gt $now -or $deadline -le $start -or $deadline -gt $start.AddHours(24) -or $now -ge $deadline) {
        throw 'PnR campaign deadline or budget policy does not permit a launch'
    }
    $attempts = @($Ledger.attempts)
    if ($attempts.Count -ge 6 -or ($RunId -and @($attempts | Where-Object { $_.run_id -ceq $RunId }).Count)) {
        throw 'PnR launch limit reached or duplicate run ID'
    }
    $controlReserved = if (@($attempts | Where-Object { $_.purpose -ceq 'same_frequency' }).Count) { 0 } else { 1 }
    $finalReserved = if (@($attempts | Where-Object { $_.purpose -ceq 'final' }).Count) { 0 } else { 1 }
    if ($Purpose -ceq 'search' -and $attempts.Count -ge (5 - $controlReserved)) {
        throw 'PnR search would consume a reserved control/final attempt'
    }
    if (($Purpose -ceq 'same_frequency' -and $finalReserved -and $attempts.Count -ge 5) -or
        ($Purpose -ceq 'final' -and $controlReserved -and $attempts.Count -ge 5)) {
        throw 'PnR launch would consume the reserved control/final attempt'
    }
    return $deadline
}

function Get-PnrCampaignSeconds {
    param([string]$Path, [string]$Purpose)
    $ledger = [IO.File]::ReadAllText($Path) | ConvertFrom-Json
    $deadline = Assert-PnrBudgetPolicy $ledger $Purpose
    $remaining = [int][Math]::Floor(($deadline - [DateTimeOffset]::UtcNow).TotalSeconds)
    if ($remaining -le 0) { throw 'Campaign deadline has elapsed' }
    return $remaining
}

function Register-PnrAttempt {
    param([string]$Path, [string]$RunId, [string]$Purpose, [string]$SnapshotPath)
    if ($Purpose -cnotin @('search','same_frequency','final')) { throw 'Invalid PnR purpose' }
    $pathFull = [IO.Path]::GetFullPath($Path)
    $item = Get-Item -LiteralPath $pathFull -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked PnR ledger' }
    $stream = [IO.File]::Open($pathFull, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true, 4096, $true)
        try { $ledger = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        $deadline = Assert-PnrBudgetPolicy $ledger $Purpose $RunId
        $attempts = @($ledger.attempts)
        $record = [ordered]@{
            number = $attempts.Count + 1; run_id = $RunId; purpose = $Purpose
            started_utc = [DateTime]::UtcNow.ToString('o'); status = 'STARTED'
            snapshot_sha256 = (Get-FileHash -LiteralPath $SnapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
            note = 'Counted before native post-synthesis invocation; failed, timed-out and cancelled launches remain counted.'
        }
        $ledger.attempts = @($attempts) + @($record)
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($ledger | ConvertTo-Json -Depth 12) + "`n")
        $stream.Position = 0
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.SetLength($bytes.Length)
        $stream.Flush($true)
        $limit = if (Test-PnrUserBudgetOverride $ledger) { 'user_override_no_limit' } else { '6' }
        Write-Output "PNR_BUDGET_CONSUMED attempt=$($record.number)/$limit purpose=$Purpose run=$RunId deadline=$($deadline.ToString('o'))"
    } finally { $stream.Dispose() }
}
