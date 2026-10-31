param(
    [string]$SearchPath,
    [string]$ModelPath,
    [string]$PfsbPath,
    [int]$Nodes = 128,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$SearchPath) {
    $SearchPath = Join-Path $root 'artifacts\pikafish-stageb-phase4-search-x86_64'
}
if (!$ModelPath) {
    $ModelPath = Join-Path (Split-Path -Parent $root) 'xiangqi_oss\Pikafish\pikafish.nnue'
}
if (!$PfsbPath) {
    $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
}
foreach ($path in @($SearchPath, $ModelPath, $PfsbPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-4 search input: $path"
    }
}
if ($Nodes -lt 16) { throw 'Nodes must be at least 16' }

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
    ('pikafish-stageb-phase4-search-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    $records = @{}
    foreach ($mode in @('0', 'verify', '1')) {
        $logPath = Join-Path $tempRoot "mode-$mode.log"
        $wslLog = Convert-ToWslPath $logPath
        $command = @"
set -eu
PIKAFISH_STAGEB_ACCEL='$mode' \
PIKAFISH_STAGEB_PACK='$wslPack' \
PIKAFISH_PHASE4_MODEL='$wslModel' \
PIKAFISH_PHASE4_NODES='$Nodes' \
'$wslSearch' >'$wslLog' 2>&1
"@.Replace("`r`n", "`n")
        # The search itself writes both streams to the per-mode log. Suppress
        # only WSL's host proxy warning, which is not part of the acceptance.
        $savedErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & wsl.exe -d $Distro -- bash -lc $command 2>$null
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedErrorPreference
        if ($exitCode -ne 0) {
            if (Test-Path -LiteralPath $logPath) { Get-Content $logPath }
            throw "Stage B phase-4 fixed-node search failed in mode $mode"
        }
        $text = [IO.File]::ReadAllText($logPath)
        Write-Output $text.TrimEnd()
        if (!$text.Contains("PIKAFISH_STAGEB_PHASE4_SEARCH_PASS mode=$mode cases=3 nodes=$Nodes")) {
            throw "Stage B phase-4 search PASS marker missing in mode $mode"
        }
        if ($mode -ne '0') {
            foreach ($needle in @('PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=',
                                  'PIKAFISH_STAGEB_ACCEL_STATS ')) {
                if (!$text.Contains($needle)) {
                    throw "Stage B phase-4 hardware marker missing in mode ${mode}: $needle"
                }
            }
            foreach ($forbidden in @('PIKAFISH_STAGEB_ACCEL_MISMATCH',
                                      'PIKAFISH_STAGEB_CPU_FALLBACK',
                                      'PIKAFISH_MAC_RUNTIME_FUSED')) {
                if ($text.Contains($forbidden)) {
                    throw "Stage B phase-4 forbidden marker in mode ${mode}: $forbidden"
                }
            }
        }

        $modeRecords = @()
        foreach ($line in ($text -split "`r?`n")) {
            if ($line -match ('^PIKAFISH_STAGEB_PHASE4_SEARCH mode=' +
                '(?<mode>0|verify|1) case=(?<case>[0-2]) ' +
                'bestmove=(?<bestmove>\S+) ponder=(?<ponder>\S*) ' +
                'score=(?<score>-?[0-9]+) wdl=(?<wdl>[0-9]+,[0-9]+,[0-9]+) ' +
                'nodes=(?<nodes>[1-9][0-9]*) elapsed_ms=(?<elapsed>[0-9]+) ' +
                'nps=(?<nps>[0-9]+)$')) {
                $modeRecords += [pscustomobject]@{
                    Case = [int]$Matches.case
                    Signature = "$($Matches.case)|$($Matches.bestmove)|" +
                        "$($Matches.ponder)|$($Matches.score)|$($Matches.wdl)|" +
                        "$($Matches.nodes)"
                    Elapsed = [uint64]$Matches.elapsed
                    Nps = [uint64]$Matches.nps
                }
            }
        }
        if ($modeRecords.Count -ne 3) {
            throw "Stage B phase-4 expected 3 fixed-node records in mode $mode"
        }
        $records[$mode] = $modeRecords | Sort-Object Case
    }

    foreach ($case in 0..2) {
        $expected = $records['0'][$case].Signature
        if ($records['verify'][$case].Signature -ne $expected -or
            $records['1'][$case].Signature -ne $expected) {
            throw "Stage B phase-4 fixed-node result mismatch in case $case"
        }
    }
    $cpuMs = ($records['0'] | Measure-Object Elapsed -Sum).Sum
    $verifyMs = ($records['verify'] | Measure-Object Elapsed -Sum).Sum
    $enabledMs = ($records['1'] | Measure-Object Elapsed -Sum).Sum
    Write-Output ("PIKAFISH_STAGEB_PHASE4_SEARCH_COMPARE_PASS cases=3 nodes=$Nodes " +
        "cpu_ms=$cpuMs verify_ms=$verifyMs enabled_ms=$enabledMs")
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
