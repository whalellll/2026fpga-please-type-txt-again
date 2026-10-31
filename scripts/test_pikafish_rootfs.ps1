param(
    [string]$RepoRoot,
    [string]$Distro = 'chiplab_sim',
    [switch]$EmbeddedOnly = $true,
    [string]$RootfsPath,
    [string]$DtsPath,
    [string]$DtbPath,
    [string]$GuiPath,
    [hashtable[]]$AdditionalPayloads = @()
)

$ErrorActionPreference = 'Stop'
if (!$RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
if (!$rootfsPath) { $rootfsPath = Join-Path $RepoRoot 'linux\boot\rootfs.cpio' }
$externalModelPath = Join-Path $RepoRoot 'linux\boot\pikafish.pff'
$attackTablePath = Join-Path $RepoRoot 'linux\boot\pikafish.atk'
if (!$dtsPath) { $dtsPath = Join-Path $RepoRoot 'linux\soc.dts' }
if (!$dtbPath) { $dtbPath = Join-Path $RepoRoot 'linux\boot\soc.dtb' }
$enginePath = Join-Path $RepoRoot 'artifacts\pikafish-rv32'
if (!$guiPath) { $guiPath = Join-Path $RepoRoot 'artifacts\xiangqi-pikafish-gui' }
$stageBPackPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-mac.bin'
$stageBLoaderPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-load'
$stageBGoldenPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-golden.bin'
$stageBBoardAcceptPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-board-accept'
$stageBPositionGoldenPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-position-golden.bin'
$stageBPositionAcceptPath = Join-Path $RepoRoot 'artifacts\pikafish-stageb-position-accept'
$overlayRoot = Join-Path $RepoRoot 'linux\rootfs_overlay'
$expectedModelHash = 'de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
$expectedModelBytes = 68122688
$expectedAttackHash = '2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c'
$expectedAttackBytes = 34603072
$requiredFiles = @($rootfsPath, $externalModelPath, $attackTablePath,
    $dtsPath, $dtbPath, $guiPath,
    $stageBPackPath, $stageBLoaderPath, $stageBGoldenPath,
    $stageBBoardAcceptPath, $stageBPositionGoldenPath,
    $stageBPositionAcceptPath)
if (!$EmbeddedOnly) {
    $requiredFiles += $enginePath
}
foreach ($path in $requiredFiles) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Pikafish rootfs regression input: $path"
    }
}

function Read-HexField([byte[]]$Bytes, [int]$Offset) {
    return [Convert]::ToUInt32(
        [Text.Encoding]::ASCII.GetString($Bytes, $Offset, 8), 16)
}

function Get-Aligned4([int64]$Value) {
    return ($Value + 3) -band (-bnot 3)
}

function Get-SliceHash(
    [byte[]]$Bytes,
    [int]$Offset,
    [int]$Length
) {
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha256.ComputeHash($Bytes, $Offset, $Length) |
            ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha256.Dispose()
    }
}

function Get-ByteHash([byte[]]$Bytes) {
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha256.ComputeHash($Bytes) |
            ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha256.Dispose()
    }
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$rootfs = [IO.File]::ReadAllBytes($rootfsPath)
if ($rootfs.Length -gt 0x01000000) {
    throw "Pikafish rootfs exceeds the 16 MiB TFTP slot: $($rootfs.Length) bytes"
}
$entries = @{}
$offset = 0
$foundTrailer = $false
while ($offset + 110 -le $rootfs.Length) {
    $magic = [Text.Encoding]::ASCII.GetString($rootfs, $offset, 6)
    if ($magic -ne '070701' -and $magic -ne '070702') {
        throw "Invalid newc header at offset $offset"
    }
    $mode = Read-HexField $rootfs ($offset + 14)
    $size = [int](Read-HexField $rootfs ($offset + 54))
    $nameSize = [int](Read-HexField $rootfs ($offset + 94))
    $nameStart = $offset + 110
    $name = [Text.Encoding]::ASCII.GetString($rootfs, $nameStart,
        $nameSize - 1)
    $dataStart = [int](Get-Aligned4 ($nameStart + $nameSize))
    $nextOffset = [int](Get-Aligned4 ($dataStart + $size))
    if ($nextOffset -gt $rootfs.Length) {
        throw "Truncated newc entry: $name"
    }
    if ($name -eq 'TRAILER!!!') {
        $foundTrailer = $true
        break
    }
    $entries[$name] = @{
        Mode = $mode
        Size = $size
        DataStart = $dataStart
    }
    $offset = $nextOffset
}
if (!$foundTrailer) { throw 'Pikafish rootfs has no TRAILER!!! entry' }

$payloadChecks = @(
    @{ Name = 'usr/bin/xiangqi-pikafish-gui'; Source = $guiPath; Mode = 0x1ed },
    @{ Name = 'usr/bin/pikafish-stageb-load'; Source = $stageBLoaderPath; Mode = 0x1ed },
    @{ Name = 'usr/bin/pikafish-stageb-board-accept'; Source = $stageBBoardAcceptPath; Mode = 0x1ed },
    @{ Name = 'usr/bin/pikafish-stageb-position-accept'; Source = $stageBPositionAcceptPath; Mode = 0x1ed },
    @{ Name = 'opt/pikafish/stageb-mac.bin'; Source = $stageBPackPath; Mode = 0x1a4 },
    @{ Name = 'opt/pikafish/stageb-golden.bin'; Source = $stageBGoldenPath; Mode = 0x1a4 },
    @{ Name = 'opt/pikafish/stageb-position-golden.bin'; Source = $stageBPositionGoldenPath; Mode = 0x1a4 },
    @{ Name = 'etc/inittab'; Source = (Join-Path $overlayRoot 'etc\inittab'); Mode = 0x1a4; NormalizeLf = $true },
    @{ Name = 'etc/profile'; Source = (Join-Path $overlayRoot 'etc\profile'); Mode = 0x1a4; NormalizeLf = $true },
    @{ Name = 'etc/init.d/rcS'; Source = (Join-Path $overlayRoot 'etc\init.d\rcS'); Mode = 0x1ed; NormalizeLf = $true },
    @{ Name = 'etc/init.d/S95pikafish'; Source = (Join-Path $overlayRoot 'etc\init.d\S95pikafish'); Mode = 0x1ed; NormalizeLf = $true },
    @{ Name = 'usr/bin/xiangqi-pikafish'; Source = (Join-Path $overlayRoot 'usr\bin\xiangqi-pikafish'); Mode = 0x1ed; NormalizeLf = $true }
)
foreach ($payload in $AdditionalPayloads) {
    if (!(Test-Path -LiteralPath $payload.Path -PathType Leaf)) {
        throw "Missing candidate payload: $($payload.Path)"
    }
    $payloadChecks += @{ Name = $payload.Name; Source = $payload.Path;
                        Mode = ([int]$payload.Mode -band 0x1ff) }
}
if (!$EmbeddedOnly) {
    $payloadChecks = @(
        @{ Name = 'usr/bin/pikafish'; Source = $enginePath; Mode = 0x1ed }
    ) + $payloadChecks
} elseif ($entries.ContainsKey('usr/bin/pikafish')) {
    throw 'Embedded-only rootfs unexpectedly contains the standalone Pikafish engine'
}
foreach ($check in $payloadChecks) {
    if (!$entries.ContainsKey($check.Name)) {
        throw "Pikafish rootfs entry is missing: $($check.Name)"
    }
    $entry = $entries[$check.Name]
    if (($entry.Mode -band 0x1ff) -ne $check.Mode) {
        throw ('Wrong mode for {0}: 0{1:o}' -f $check.Name,
            ($entry.Mode -band 0x1ff))
    }
    if ($check.Source) {
        $source = Get-Item -LiteralPath $check.Source
        [byte[]]$sourceBytes = [IO.File]::ReadAllBytes($source.FullName)
        if ($check.NormalizeLf) {
            $sourceText = [Text.Encoding]::UTF8.GetString($sourceBytes)
            $sourceText = $sourceText.Replace("`r`n", "`n").Replace("`r", "`n")
            $sourceBytes = [Text.UTF8Encoding]::new($false).GetBytes($sourceText)
        }
        if ($entry.Size -ne $sourceBytes.Length) {
            throw "Wrong size for $($check.Name): $($entry.Size)"
        }
        $expectedHash = Get-ByteHash $sourceBytes
    } elseif ($check.Hash) {
        $expectedHash = $check.Hash
    } else {
        continue
    }
    $actualHash = Get-SliceHash $rootfs $entry.DataStart $entry.Size
    if ($actualHash -ne $expectedHash) {
        throw "Hash mismatch for $($check.Name): $actualHash"
    }
    if ($check.NormalizeLf) {
        for ($index = 0; $index -lt $entry.Size; $index++) {
            if ($rootfs[$entry.DataStart + $index] -eq 13) {
                throw "Carriage return found in POSIX text entry: $($check.Name)"
            }
        }
    }
}

if ($entries.ContainsKey('opt/pikafish/pikafish.nnue')) {
    throw 'Pikafish rootfs unexpectedly contains the external PFF1 model'
}
if ($entries.ContainsKey('usr/bin/pff1-linux-probe')) {
    throw 'Pikafish rootfs unexpectedly contains the retired PFF1 probe'
}
$externalModel = Get-Item -LiteralPath $externalModelPath
$externalModelHash = (Get-FileHash -LiteralPath $externalModelPath `
    -Algorithm SHA256).Hash.ToLowerInvariant()
$externalModelHeader = [IO.File]::ReadAllBytes($externalModelPath)[0..3]
if ($externalModel.Length -ne $expectedModelBytes -or
    $externalModelHash -ne $expectedModelHash -or
    [Text.Encoding]::ASCII.GetString($externalModelHeader) -ne 'PFF1') {
    throw 'External SD PFF1 model has the wrong size, hash, or header'
}
$attackTable = Get-Item -LiteralPath $attackTablePath
$attackHash = (Get-FileHash -LiteralPath $attackTablePath `
    -Algorithm SHA256).Hash.ToLowerInvariant()
if ($attackTable.Length -ne $expectedAttackBytes -or
    $attackHash -ne $expectedAttackHash) {
    throw 'External SD PFA1 attack table has the wrong size or hash'
}
$attackVerifier = Join-Path $RepoRoot 'linux\pikafish\verify_attack_tables.py'
& wsl.exe -d $Distro -- python3 (Convert-ToWslPath $attackVerifier) `
    (Convert-ToWslPath $attackTablePath)
if ($LASTEXITCODE -ne 0) {
    throw 'External SD PFA1 attack-table format validation failed'
}

$startupEntry = $entries['etc/init.d/S95pikafish']
$startupText = [Text.Encoding]::UTF8.GetString(
    $rootfs, $startupEntry.DataStart, $startupEntry.Size)
foreach ($needle in @(
    '/usr/bin/xiangqi-pikafish </dev/null >/dev/console 2>&1 &',
    'PIDFILE=/run/xiangqi-pikafish.pid',
    'CONTROL_FIFO=/run/xiangqi-pikafish.in',
    'mkfifo "$CONTROL_FIFO"',
    'PIKAFISH_STAGEB_ACCEL="${PIKAFISH_STAGEB_ACCEL:-1}"',
    'export PIKAFISH_STAGEB_ACCEL',
    'Full Pikafish GUI launched: pid=')) {
    if (!$startupText.Contains($needle)) {
        throw "Pikafish init script does not auto-start the GUI: $needle"
    }
}
if ($startupText.Contains('/usr/bin/pikafish-stageb-load') -or
    $startupText.Contains('/run/pikafish-stageb.ready')) {
    throw 'Pikafish init script still preloads unused Stage B data'
}
$inittabEntry = $entries['etc/inittab']
$inittabText = [Text.Encoding]::UTF8.GetString(
    $rootfs, $inittabEntry.DataStart, $inittabEntry.Size)
if ($inittabText.Contains('mount -t devtmpfs devtmpfs /dev')) {
    throw 'Pikafish inittab redundantly mounts the kernel-provided devtmpfs'
}

$expectedEnd = 0x03000000L + $rootfs.Length
$expectedEndText = '0x{0:x8}' -f $expectedEnd
$dts = [IO.File]::ReadAllText($dtsPath)
if ($dts -notmatch ('linux,initrd-end\s*=\s*<' + $expectedEndText + '>')) {
    throw "DTS initrd end does not match rootfs: expected $expectedEndText"
}
if ($dts -notmatch 'timebase-frequency\s*=\s*<59400000>' -or
    $dts -match 'clocksource=jiffies') {
    throw 'DTS TIME CSR frequency or Linux clocksource is stale'
}
if ($dts -notmatch 'pikafish-pff1@10000000' -or
    $dts -notmatch 'reg\s*=\s*<0x10000000\s+0x05000000>' -or
    $dts -notmatch 'no-map\s*;') {
    throw 'DTS does not reserve the 80 MiB physical PFF1 DMA region'
}
if ($dts -notmatch 'pikafish-attacks@15000000' -or
    $dts -notmatch 'reg\s*=\s*<0x15000000\s+0x02200000>') {
    throw 'DTS does not reserve the 34 MiB physical PFA1 DMA region'
}
if ($dts -notmatch 'pango,cpu-alias\s*=\s*<0x9b000000>') {
    throw 'DTS lacks the uncached MAC scratch alias required by the kernel driver'
}
$ErrorActionPreference = 'Continue'
$dtbEndText = (& wsl.exe -d $Distro -- fdtget -t x `
    (Convert-ToWslPath $dtbPath) /chosen linux,initrd-end 2>$null) -join ''
$fdtgetExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$dtbEndText = $dtbEndText.Trim()
if ($fdtgetExitCode -ne 0 -or $dtbEndText -notmatch '^[0-9a-fA-F]+$' -or
    [Convert]::ToUInt32($dtbEndText, 16) -ne $expectedEnd) {
    throw "DTB initrd end does not match rootfs: expected $expectedEndText"
}
$ErrorActionPreference = 'Continue'
$dtbTimebaseText = (& wsl.exe -d $Distro -- fdtget -t x `
    (Convert-ToWslPath $dtbPath) /cpus timebase-frequency 2>$null) -join ''
$fdtgetExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($fdtgetExitCode -ne 0 -or $dtbTimebaseText.Trim() -ne '38a5f40') {
    throw "DTB TIME CSR frequency is stale: $dtbTimebaseText"
}
$ErrorActionPreference = 'Continue'
$dtbMacAlias = (& wsl.exe -d $Distro -- fdtget -t x `
    (Convert-ToWslPath $dtbPath) /soc/mac-accel@1fe10000 pango,cpu-alias 2>$null) -join ''
$fdtgetExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($fdtgetExitCode -ne 0 -or $dtbMacAlias.Trim() -ne '9b000000') {
    throw "DTB MAC scratch alias differs from the kernel driver ABI: $dtbMacAlias"
}
$ErrorActionPreference = 'Continue'
$dtbAttackReg = (& wsl.exe -d $Distro -- fdtget -t x `
    (Convert-ToWslPath $dtbPath) /reserved-memory/pikafish-attacks@15000000 reg `
    2>$null) -join ' '
$fdtgetAttackExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($fdtgetAttackExitCode -ne 0 -or
    $dtbAttackReg.Trim() -notmatch '^15000000\s+2200000$') {
    throw "DTB PFA1 reservation mismatch: $dtbAttackReg"
}

$bootMain = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'sw\bootloader\main.c'))
if ($rootfs.Length -gt 0x01000000 -or
    !$bootMain.Contains('"rootfs.cpio",0x03000000u,0x01000000u') -or
    !$bootMain.Contains('"fw_jump.bin",0x18000000u,0x00100000u') -or
    !$bootMain.Contains('"soc.dtb",0x1a000000u,0x00100000u')) {
    throw 'S-mode Linux TFTP boot payload addresses or limits changed'
}
$guiSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\xiangqi_pikafish_gui.c'))
$embeddedSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_embedded.cpp'))
$sbiPatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\opensbi\0001-pg2l-time-cycle-bridge.patch'))
foreach ($needle in @('get_ticks()', 'timer_dev->timer_value()',
        '(remaining / 6) * 5', 'timer_dev->timer_event_start(mtime_deadline)')) {
    if (!$sbiPatch.Contains($needle)) {
        throw "OpenSBI CPU TIME to CLINT timer bridge missing: $needle"
    }
}
if ((Get-Item -LiteralPath (Join-Path $RepoRoot 'linux\boot\fw_jump.bin')).Length -gt 0x00100000) {
    throw 'OpenSBI exceeds the bootloader TFTP slot'
}
$firmwareHash = (Get-FileHash -LiteralPath `
    (Join-Path $RepoRoot 'linux\boot\fw_jump.bin') -Algorithm SHA256).Hash
if ($firmwareHash -ne '5419099F34B3296F2750876DEF9F23935C5D66B974A063BCDE72687D1101947E') {
    throw "OpenSBI firmware differs from the board-tested timer bridge: $firmwareHash"
}
if (!$guiSource.Contains(
        '#define ENGINE_MODEL           "pff1-view:0x10000000:68122688"')) {
    throw 'GUI does not use the cacheable read-only PFF1 DDR view'
}
foreach ($needle in @(
    'XQ_GUI_COMMAND_MOVE',
    'XQ LINUX INPUT FIFO READY',
    'XQ LINUX INJECT MOVE_PASS',
    'xq_pikafish_apply_move(board, command->move, NULL)')) {
    if (!$guiSource.Contains($needle)) {
        throw "GUI software move-injection contract missing: $needle"
    }
}
$initialDraw = $guiSource.IndexOf('xq_fb_gui_show(&board, -1, -1, red_score, nodes,')
$asyncStart = $guiSource.IndexOf('if (!start_engine_async())')
if ($initialDraw -lt 0 -or $asyncStart -lt 0 -or $initialDraw -ge $asyncStart -or
    !$guiSource.Contains('Model loading stays asynchronous so input and scanout remain live.')) {
    throw 'GUI must draw and initialize input before asynchronous engine loading'
}
foreach ($needle in @(
    'map_precomputed_attack_tables(attackTableMapping',
    'Stockfish::Attacks::init_precomputed(',
    'report_init_stage("attacks-map-ready");',
    'std::nullopt, hashMiB,',
    'std::make_optional(std::filesystem::path(modelPath))',
    'report_init_stage("constructor-ready");')) {
    if (!$embeddedSource.Contains($needle)) {
        throw "Embedded engine initialization diagnostic missing: $needle"
    }
}
foreach ($redundant in @(
    'set_option(*next, "Threads", "1");',
    'set_option(*next, "Hash", std::to_string(hashMiB));',
    'set_option(*next, "EvalFile", modelPath);',
    'next->search_clear();')) {
    if ($embeddedSource.Contains($redundant)) {
        throw "Embedded engine initialization still contains redundant work: $redundant"
    }
}
$flatSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_flat_nnue.inc'))
$viewPatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish-view.patch'))
$embeddedPatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish-embedded.patch'))
$memoryPatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish-embedded-memory.patch'))
$startupMemoryPatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish-startup-memory.patch'))
$zeroStatePatch = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish-zero-state-history.patch'))
if (!$flatSource.Contains('PIKAFISH_PFF1_FEATURE_CRC_SKIPPED') -or
    !$flatSource.Contains('reason=sd-crc16-host-verified') -or
    !$flatSource.Contains('reportStage("mlps-crc-ready");') -or
    !$viewPatch.Contains('hashing their large payload is redundant')) {
    throw 'Embedded PFF1 fast-path contract is incomplete'
}
foreach ($needle in @(
    'inline bool read_pff1_direct(',
    'read_parameters_flat(const char*& cursor, const char* end)',
    'return read_pff1_direct(cursor, end, weights, sizeof(weights));')) {
    if (!$embeddedPatch.Contains($needle)) {
        throw "Embedded PFF1 MLP direct-parse contract missing: $needle"
    }
}
foreach ($needle in @(
    'PIKAFISH_EMBEDDED_SINGLE_THREAD',
    'int InitialValue = 0',
    'OffsetAtomicStats<i16, 8192, -1247',
    'std::memset(&continuationHistory',
    'clear(bool freshHistoryStorage = false)')) {
    if (!$zeroStatePatch.Contains($needle)) {
        throw "Embedded zero-state history refactor missing: $needle"
    }
}
$pikafishBuildDriver = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\build_in_wsl.sh'))
$historyTestSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_history_zero_test.cpp'))
if (!$pikafishBuildDriver.Contains('pikafish_history_zero_test.cpp') -or
    !$pikafishBuildDriver.Contains('PIKAFISH_EMBEDDED_SINGLE_THREAD') -or
    !$historyTestSource.Contains('PIKAFISH_HISTORY_ZERO_STATE_TEST_PASS')) {
    throw 'Embedded zero-state history unit test is missing'
}
foreach ($needle in @(
    'stage=shared-histories-alloc-start bytes=41230336',
    'report("shared-pawn-clear-start")',
    'report("shared-continuation-clear-start")')) {
    if (!$memoryPatch.Contains($needle)) {
        throw "Embedded memory diagnostic missing: $needle"
    }
}
foreach ($needle in @(
    'stage=threadpool-initial-clear-start',
    'stage=tt-fresh-zero-skip',
    '(void) network;',
    '#if !defined(PIKAFISH_EMBEDDED_GUI)',
    'ThreatOffsets;')) {
    if (!$startupMemoryPatch.Contains($needle)) {
        throw "Embedded startup-memory optimization missing: $needle"
    }
}
$stageASource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_stagea_accel.cpp'))
foreach ($redundant in @(
    'ControlClear',
    'std::memset(input',
    'std::memset(weights')) {
    if ($stageASource.Contains($redundant)) {
        throw "Stage A still contains redundant scratch work: $redundant"
    }
}
$stageBLoaderSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_stageb_load.c'))
if ($stageBLoaderSource.Contains('memset(ddr, 0, PF_STAGEB_DDR_BYTES)') -or
    !$stageBLoaderSource.Contains(
        'mmap(NULL, PF_STAGEB_PACK_USED_BYTES, PROT_READ | PROT_WRITE')) {
    throw 'Manual Stage B loader still clears or maps the unused DDR tail'
}
$stageBBoardSource = [IO.File]::ReadAllText(
    (Join-Path $RepoRoot 'linux\pikafish\pikafish_stageb_board_accept.c'))
foreach ($needle in @(
    'PIKAFISH_STAGEB_BOARD_GOLDEN_PASS',
    'PF_STAGEB_GOLDEN_STACK_COUNT',
    'scratch_canaries_ok',
    'pfsb-ddr-mutated')) {
    if (!$stageBBoardSource.Contains($needle)) {
        throw "Stage B board golden acceptance contract missing: $needle"
    }
}
if ($guiSource.Contains('map_physical(fd, VIDEO_FB1_CPU_UNCACHED') -or
    $guiSource.Contains('memset(&result, 0, sizeof(result))')) {
    throw 'GUI still maps or clears unused direct-core state'
}
$statusFunction = [regex]::Match($embeddedSource,
    'extern "C" int pikafish_embedded_status\(void\)\s*\{(?<body>.*?)\n\}',
    [Text.RegularExpressions.RegexOptions]::Singleline)
$stopFunction = [regex]::Match($embeddedSource,
    'extern "C" void pikafish_embedded_stop\(void\)\s*\{(?<body>.*?)\n\}',
    [Text.RegularExpressions.RegexOptions]::Singleline)
if (!$statusFunction.Success -or !$stopFunction.Success -or
    !$statusFunction.Groups['body'].Value.Contains(
        'engineStatus.load(std::memory_order_acquire)') -or
    $statusFunction.Groups['body'].Value -match '\bjoin\s*\(' -or
    $statusFunction.Groups['body'].Value.Contains('reap_loader_thread') -or
    !$stopFunction.Groups['body'].Value.Contains('loaderThread->join();') -or
    !$stopFunction.Groups['body'].Value.Contains('loaderThread.reset();') -or
    !$embeddedSource.Contains('Do not retain the startup')) {
    throw 'Embedded GUI status must be nonblocking, with loader join deferred to stop and callback lifetime bounded'
}
foreach ($needle in @(
    'mlp_direct_bytes=',
    'PIKAFISH_PFF1_MLPS_STACK_READY stack=',
    'network[i].read_parameters_flat(mlpCursor, mlpsEnd)')) {
    if (!$flatSource.Contains($needle)) {
        throw "Embedded PFF1 MLP zero-copy contract missing: $needle"
    }
}

Write-Output ("PIKAFISH_ROOTFS_REGRESSION_PASS bytes={0} initrd_end={1}" -f `
    $rootfs.Length, $expectedEndText)
Write-Output "PIKAFISH_EXTERNAL_MODEL_SHA256=$expectedModelHash"
Write-Output "PIKAFISH_ATTACK_TABLE_SHA256=$expectedAttackHash"
