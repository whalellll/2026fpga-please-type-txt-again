param(
    [string]$SearchPath,
    [string]$ModelPath,
    [string]$PfsbPath,
    [int]$Nodes = 128,
    [int]$LongNodes = 4096,
    [int]$Rounds = 4,
    [int]$ResetBudgetMilliseconds = 250,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$SearchPath) {
    $SearchPath = Join-Path $root 'artifacts\pikafish-stageb-phase5-search-x86_64'
}
if (!$ModelPath) {
    $ModelPath = Join-Path (Split-Path -Parent $root) 'xiangqi_oss\Pikafish\pikafish.nnue'
}
if (!$PfsbPath) {
    $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
}
foreach ($path in @($SearchPath, $ModelPath, $PfsbPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-5 search input: $path"
    }
}
if ($Nodes -lt 16 -or $LongNodes -lt $Nodes -or $Rounds -lt 1 -or
    $ResetBudgetMilliseconds -lt 1 -or $ResetBudgetMilliseconds -gt 60000) {
    throw 'Invalid phase-5 nodes/long-nodes/rounds'
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$wslSearch = Convert-ToWslPath $SearchPath
$wslModel = Convert-ToWslPath $ModelPath
$wslPack = Convert-ToWslPath $PfsbPath
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) `
    ('pikafish-stageb-phase5-search-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    $signatures = @{}
    $expectedCheckpoints = $Rounds * 2 + 5
    foreach ($mode in @('0', 'verify', '1')) {
        $logPath = Join-Path $tempRoot "mode-$mode.log"
        $wslLog = Convert-ToWslPath $logPath
        $command = @"
set -eu
PIKAFISH_STAGEB_ACCEL='$mode' \
PIKAFISH_STAGEB_PACK='$wslPack' \
PIKAFISH_PHASE5_MODEL='$wslModel' \
PIKAFISH_PHASE5_NODES='$Nodes' \
PIKAFISH_PHASE5_LONG_NODES='$LongNodes' \
PIKAFISH_PHASE5_ROUNDS='$Rounds' \
PIKAFISH_PHASE5_RESET_BUDGET_MS='$ResetBudgetMilliseconds' \
'$wslSearch' >'$wslLog' 2>&1
"@.Replace("`r`n", "`n")
        $savedErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & wsl.exe -d $Distro -- bash -lc $command 2>$null
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedErrorPreference
        if ($exitCode -ne 0) {
            if (Test-Path -LiteralPath $logPath) { Get-Content $logPath }
            throw "Stage B phase-5 search failed in mode $mode"
        }
        $text = [IO.File]::ReadAllText($logPath)
        Write-Output $text.TrimEnd()
        $pass = "PIKAFISH_STAGEB_PHASE5_SEARCH_PASS mode=$mode cases=8 " +
            "rounds=$Rounds nodes=$Nodes long_nodes=$LongNodes game=terminal"
        if (!$text.Contains($pass)) {
            throw "Stage B phase-5 search PASS marker missing in mode $mode"
        }
        $resetRecords = [regex]::Matches(
            $text,
            '^PIKAFISH_STAGEB_PHASE5_RESET .+$',
            [Text.RegularExpressions.RegexOptions]::Multiline)
        if ($resetRecords.Count -ne $Rounds + 2) {
            throw "Expected $($Rounds + 2) bounded phase-5 resets in mode $mode, got $($resetRecords.Count)"
        }
        $firstReset = $text.IndexOf('PIKAFISH_STAGEB_PHASE5_STAGE mode=' + $mode +
                                    ' stage=new-game-start')
        if ($firstReset -lt 0) {
            throw "Stage B phase-5 first new-game marker missing in mode $mode"
        }
        if ($text.Substring($firstReset).Contains(
                'ENGINE DETAIL stage=worker-clear-start')) {
            throw "Stage B phase-5 new-game path performed a blocking history clear in mode $mode"
        }
        if (!$text.Contains('PIKAFISH_STAGEB_PHASE5_GAME mode=' + $mode +
                            ' first=1 second=1 bestmove=(none)')) {
            throw "Stage B phase-5 complete-game terminal marker missing in mode $mode"
        }
        if ($mode -ne '0') {
            foreach ($needle in @('PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=',
                                  "PIKAFISH_STAGEB_HEALTH checkpoints=$expectedCheckpoints " +
                                      'checkpoint_failures=0')) {
                if (!$text.Contains($needle)) {
                    throw "Stage B phase-5 hardware marker missing in mode ${mode}: $needle"
                }
            }
            foreach ($forbidden in @('PIKAFISH_STAGEB_ACCEL_MISMATCH',
                                      'PIKAFISH_STAGEB_CPU_FALLBACK',
                                      'PIKAFISH_MAC_RUNTIME_FUSED')) {
                if ($text.Contains($forbidden)) {
                    throw "Stage B phase-5 forbidden marker in mode ${mode}: $forbidden"
                }
            }
        }

        $modeSignatures = @()
        foreach ($line in ($text -split "`r?`n")) {
            if ($line -match ('^PIKAFISH_STAGEB_PHASE5_(CASE|LONG|GAME) mode=' +
                              [regex]::Escape($mode) + ' (?<body>.*)$')) {
                $modeSignatures += ($Matches[1] + '|' +
                    ($Matches.body -replace ' elapsed_ms=[0-9]+$', ''))
            }
        }
        $expectedCount = $Rounds * 8 + 3
        if ($modeSignatures.Count -ne $expectedCount) {
            throw "Expected $expectedCount phase-5 records in mode $mode, got $($modeSignatures.Count)"
        }
        $signatures[$mode] = @($modeSignatures)
    }

    $expected = $signatures['0'] -join "`n"
    if (($signatures['verify'] -join "`n") -ne $expected -or
        ($signatures['1'] -join "`n") -ne $expected) {
        throw 'Stage B phase-5 CPU/verify/enabled result mismatch'
    }
    Write-Output ("PIKAFISH_STAGEB_PHASE5_SEARCH_COMPARE_PASS cases=8 " +
        "rounds=$Rounds nodes=$Nodes long_nodes=$LongNodes game=terminal")
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
