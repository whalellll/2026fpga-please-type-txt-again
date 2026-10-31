# Optional execution history only. No launch cap, reserved slots or campaign deadline.
# Per-process timeouts and correctness/STA/board gates belong to their own helpers.
function Resolve-PnrHistoryPath {
    param([string]$Root, [string]$Requested)
    if (!$Requested) { return '' }
    $full = if ([IO.Path]::IsPathRooted($Requested)) {
        [IO.Path]::GetFullPath($Requested)
    } else { [IO.Path]::GetFullPath((Join-Path $Root $Requested)) }
    $cursor = $full
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and
            ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Linked PnR history path'
        }
        $cursor = Split-Path -Parent $cursor
    }
    if (!(Test-Path -LiteralPath (Split-Path -Parent $full) -PathType Container)) {
        throw 'PnR history parent directory does not exist'
    }
    if ((Test-Path -LiteralPath $full) -and !(Test-Path -LiteralPath $full -PathType Leaf)) {
        throw 'PnR history path is not a file'
    }
    return $full
}

function Register-PnrAttempt {
    param([string]$Path, [string]$RunId,
        [ValidateSet('search','same_frequency','final')][string]$Purpose,
        [string]$SnapshotPath)
    if ([string]::IsNullOrWhiteSpace($RunId)) { throw 'Missing PnR run ID' }
    $pathFull = Resolve-PnrHistoryPath (Get-Location).Path $Path
    $snapshotHash = (Get-FileHash -LiteralPath $SnapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $stream = [IO.File]::Open($pathFull, [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        if ($stream.Length) {
            $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true, 4096, $true)
            try { $ledger = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        } else { $ledger = [pscustomobject]@{schema=1;attempts=@()} }
        if ($ledger.schema -ne 1 -or !$ledger.PSObject.Properties['attempts']) {
            throw 'Invalid PnR history schema'
        }
        $attempts = @($ledger.attempts)
        if (@($attempts | Where-Object { $_.run_id -ceq $RunId }).Count) {
            throw 'Duplicate PnR history run ID'
        }
        # Legacy maximum/deadline/user_override fields, if present in an old
        # history file, are preserved as historical metadata and never enforced.
        $record = [ordered]@{
            number=$attempts.Count+1;run_id=$RunId;purpose=$Purpose
            started_utc=[DateTime]::UtcNow.ToString('o');status='STARTED'
            snapshot_sha256=$snapshotHash
            note='Execution history only; failed, timed-out and cancelled runs remain recorded.'
        }
        $ledger.attempts = @($attempts) + @($record)
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($ledger | ConvertTo-Json -Depth 12) + "`n")
        $stream.Position=0; $stream.Write($bytes,0,$bytes.Length)
        $stream.SetLength($bytes.Length); $stream.Flush($true)
        Write-Output "PNR_ATTEMPT_RECORDED number=$($record.number) purpose=$Purpose run=$RunId"
    } finally { $stream.Dispose() }
}
