# Launch a fixed release owner through WMI so an exec_command session Job cannot
# close it. The target scripts keep their own bounded kill-on-close Windows Jobs.
# owner_receipt.json records process completion, not FPGA/CoreMark acceptance.
param(
    [ValidateSet('Start','Status','Stop','Worker','SelfTest')][string]$Action = 'Status',
    [ValidateSet('Fpga','LongCoreMark','Fixture')][string]$Job = '',
    [string]$JobId = '',
    [string]$ManifestSha256 = '',
    [ValidateRange(1,10)][int]$FixtureSeconds = 2,
    [ValidateSet('Success','NativeNonzero','PowerShellError')][string]$FixtureMode = 'Success',
    [ValidateRange(1,86400)][int]$PdsTimeoutSeconds = 14400,
    [string]$PdsShell = '',
    [string]$PythonPath = '',
    [string]$ToolchainRoot = '',
    [string]$CampaignBudget = '',
    [ValidateSet('search','same_frequency','final')][string]$AttemptPurpose = 'search',
    [string]$Distro = 'chiplab_sim',
    [ValidateRange(3600,86400)][int]$TimeoutSeconds = 14400,
    [ValidateRange(600000000,1500000000)][int]$MaxCycles = 1200000000,
    [ValidateRange(1,1000000000)][int]$CpuHz = 49500000,
    [ValidateRange(0,1000000)][int]$Iterations = 0,
    [ValidateRange(1,2)][int]$BuildJobs = 2,
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$OutputDirectory = '',
    [string]$ReleaseEvidenceDirectory = '',
    [string]$ReuseModelDirectory = ''
)

$ErrorActionPreference = 'Stop'
$Action = switch ($Action.ToLowerInvariant()) {
    'start' { 'Start' }
    'status' { 'Status' }
    'stop' { 'Stop' }
    'worker' { 'Worker' }
    'selftest' { 'SelfTest' }
}
if ($Job) {
    $Job = switch ($Job.ToLowerInvariant()) {
        'fpga' { 'Fpga' }
        'longcoremark' { 'LongCoreMark' }
        'fixture' { 'Fixture' }
    }
}
$FixtureMode = switch ($FixtureMode.ToLowerInvariant()) {
    'success' { 'Success' }
    'nativenonzero' { 'NativeNonzero' }
    'powershellerror' { 'PowerShellError' }
}
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$storeRoot = Join-Path $root 'artifacts/selftest/detached_release_jobs'
$fpgaLockPath = Join-Path $storeRoot 'fpga_owner.lock'
$launcherPath = [IO.Path]::GetFullPath($PSCommandPath)
$launcherBoundParameters = @($PSBoundParameters.Keys)
$shaPattern = '^[0-9a-f]{64}$'
$idPattern = '^[0-9a-f]{32}$'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-JsonOnce([string]$Path, $Value) {
    if (Test-Path -LiteralPath $Path) { throw "Refusing to overwrite $Path" }
    $temporary = $Path + '.tmp-' + [guid]::NewGuid().ToString('N')
    try {
        [IO.File]::WriteAllText($temporary,
            ($Value | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temporary, $Path)
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
}

function Assert-OnlyParameters([string[]]$Allowed) {
    foreach ($name in $launcherBoundParameters) {
        if ($name -notin $Allowed) { throw "-$name is not valid for $Action/$Job" }
    }
}

function Assert-ChildPath([string]$Path, [string]$Parent) {
    if (![IO.Path]::IsPathRooted($Path)) { throw "Absolute path required: $Path" }
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (!$full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path must be beneath $Parent : $full"
    }
    $cursor = $full
    $rootPath = $root.TrimEnd('\')
    while ($cursor.Length -ge $rootPath.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse point not allowed in job path: $cursor"
            }
        }
        if ($cursor.Equals($rootPath, [StringComparison]::OrdinalIgnoreCase)) { break }
        $next = Split-Path -Parent $cursor
        if ($next -eq $cursor -or !$next) { break }
        $cursor = $next
    }
    return $full
}

function Assert-ToolPath([string]$Path, [bool]$Directory, [string]$Label) {
    if (![IO.Path]::IsPathRooted($Path) -or $Path.Contains('"')) {
        throw "$Label requires an absolute path without quotes"
    }
    $full = [IO.Path]::GetFullPath($Path)
    $type = if ($Directory) { 'Container' } else { 'Leaf' }
    if (!(Test-Path -LiteralPath $full -PathType $type)) { throw "Missing $Label : $full" }
    return $full
}

function Resolve-PdsGuardPath([string]$Path) {
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or $Path.Contains('"')) {
        throw 'PDS project identity requires an absolute local path'
    }
    $full = [IO.Path]::GetFullPath($Path.Replace('/', '\'))
    if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "PDS identity contains a reparse point: $cursor"
            }
        }
        $next = Split-Path -Parent $cursor
        if (!$next -or $next -eq $cursor) { break }
        $cursor = $next
    }
    return $full
}

function Get-PdsProcessGuardDecision([string]$RepositoryRoot, $Evidence) {
    $decision = [ordered]@{pid=$Evidence.process_id; name=$Evidence.name; allowed=$false; reason='UNKNOWN_PDS_ACTIVITY'}
    try {
        if ($Evidence.name -ine 'pds.exe') { throw 'PDS CLI or unknown engine is active' }
        if (!$Evidence.stable -or !$Evidence.responding -or @($Evidence.child_ids).Count -ne 0) {
            throw "GUI identity/activity is unresolved: stable=$($Evidence.stable), responding=$($Evidence.responding), children=$(@($Evidence.child_ids).Count)"
        }
        # Require the current window title as well as launch argv: a GUI may
        # have opened another project after it was launched.
        $commandMatch = [regex]::Match([string]$Evidence.command_line,
            '(?i)\s-project\s+(?:"(?<path>[^"]+\.pds)"|(?<path>[^\s"]+\.pds))\s*$')
        $titleMatch = [regex]::Match([string]$Evidence.window_title,
            '^Pango Design Suite [^\r\n]+? - (?<path>[A-Za-z]:[/\\].+\.pds) \(on [^)]+\)$')
        if (!$commandMatch.Success -or !$titleMatch.Success) { throw 'GUI project identity is unavailable' }
        $project = Resolve-PdsGuardPath $commandMatch.Groups['path'].Value
        $titleProject = Resolve-PdsGuardPath $titleMatch.Groups['path'].Value
        if (!$project.Equals($titleProject, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'GUI title and launch project differ'
        }
        if (!(Test-Path -LiteralPath $project -PathType Leaf)) { throw 'GUI project file is missing' }
        $repository = Resolve-PdsGuardPath $RepositoryRoot
        $projectDirectory = Split-Path -Parent $project
        $projectText = Get-Content -LiteralPath $project -Raw -Encoding UTF8
        $paths = @($projectDirectory)
        foreach ($option in @('prj_work_dir','prj_impl_dir')) {
            $matches = [regex]::Matches($projectText, '\(_option\s+' + $option + '\s+\(_string\s+"([^"]+)"\)\s*\)')
            if ($matches.Count -ne 1) { throw "GUI $option is ambiguous or missing" }
            $value = $matches[0].Groups[1].Value
            $path = if ([IO.Path]::IsPathRooted($value)) { $value } else { Join-Path $projectDirectory $value }
            $paths += Resolve-PdsGuardPath $path
        }
        foreach ($path in $paths) {
            if ($path.Equals($repository, [StringComparison]::OrdinalIgnoreCase) -or
                $path.StartsWith($repository + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $repository.StartsWith($path.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'GUI project/work/implementation directory overlaps this repository'
            }
        }
        $decision.allowed = $true
        $decision.reason = 'DISTINCT_GUI_NO_CHILDREN'
        $decision.project = $project
        $decision.work_and_implementation_paths = $paths
    } catch { $decision.reason = $_.Exception.Message }
    return [pscustomobject]$decision
}

function Assert-PdsProcessAvailability([string]$RepositoryRoot) {
    $snapshot = @(Get-CimInstance Win32_Process)
    $pds = @($snapshot | Where-Object { $_.Name -in @('pds.exe','pds_shell.exe') })
    $evidence = @()
    foreach ($entry in $pds) {
        $item = [ordered]@{process_id=[int]$entry.ProcessId; name=[string]$entry.Name
            command_line=[string]$entry.CommandLine; window_title=''; responding=$false
            stable=$false; cpu_delta_ticks=-1; child_ids=@()
        }
        if ($entry.Name -ieq 'pds.exe') {
            try {
                $process = Get-Process -Id $entry.ProcessId -ErrorAction Stop
                $item.window_title = $process.MainWindowTitle
                $item.start_filetime = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
                $item.cpu_start_ticks = $process.TotalProcessorTime.Ticks
                $item.responding = $process.Responding
            } catch { $item.capture_error = $_.Exception.Message }
        }
        $evidence += $item
    }
    if (@($pds | Where-Object { $_.Name -ieq 'pds.exe' }).Count) { Start-Sleep -Milliseconds 1000 }
    $after = @(Get-CimInstance Win32_Process)
    foreach ($item in $evidence) {
        $item.child_ids = @(@($snapshot) + @($after) | Where-Object {
            $_.ParentProcessId -eq $item.process_id
        } | Select-Object -ExpandProperty ProcessId -Unique)
        if ($item.name -ieq 'pds.exe' -and $item.Contains('start_filetime')) {
            try {
                $process = Get-Process -Id $item.process_id -ErrorAction Stop
                $item.cpu_delta_ticks = $process.TotalProcessorTime.Ticks - $item.cpu_start_ticks
                $current = @($after | Where-Object { $_.ProcessId -eq $item.process_id })
                $item.stable = $current.Count -eq 1 -and $current[0].CommandLine -ceq $item.command_line -and
                    $process.StartTime.ToUniversalTime().ToFileTimeUtc() -eq $item.start_filetime -and
                    $process.MainWindowTitle -ceq $item.window_title
                $item.responding = $item.responding -and $process.Responding
            } catch { $item.capture_error = $_.Exception.Message }
        }
    }
    # Also reject a PDS process which appeared during the bounded sample.
    foreach ($entry in @($after | Where-Object { $_.Name -in @('pds.exe','pds_shell.exe') })) {
        if ($entry.ProcessId -notin @($evidence | ForEach-Object { $_.process_id })) {
            $evidence += [ordered]@{process_id=$entry.ProcessId; name=$entry.Name; stable=$false
                responding=$false; cpu_delta_ticks=-1; child_ids=@(); command_line=$entry.CommandLine; window_title=''}
        }
    }
    $decisions = @($evidence | ForEach-Object { Get-PdsProcessGuardDecision $RepositoryRoot $_ })
    $blocked = @($decisions | Where-Object { !$_.allowed })
    if ($blocked.Count) { throw ('PDS process guard rejected concurrent activity: ' + ($blocked | ConvertTo-Json -Compress -Depth 5)) }
    # CPU usage is recorded only: an idle GUI can refresh its widgets, so it
    # cannot establish whether a compiler is active. Project isolation and
    # process identity/children are the guard's acceptance conditions.
    return [ordered]@{checked_utc=[DateTime]::UtcNow.ToString('o'); sample_delay_milliseconds=1000
        status='PASS'; evidence=$evidence; decisions=$decisions
        limitation='Launch-time observation only; do not open this repository in a GUI or start another PDS task during the build.'}
}

function Get-JobDirectory([string]$Id) {
    if ($Id -cnotmatch $idPattern) { throw 'JobId must be 32 lowercase hex digits' }
    return Assert-ChildPath (Join-Path $storeRoot $Id) $root
}

function Get-VerifiedOwner($JobDirectory, $Launch) {
    if (!$Launch -or !$Launch.pid -or !$Launch.start_filetime_utc) { return $null }
    $process = Get-Process -Id ([int]$Launch.pid) -ErrorAction SilentlyContinue
    if (!$process) { return $null }
    try { $null = $process.Handle } catch { return $null }
    if ($process.ProcessName -cne 'powershell' -or
        $process.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [long]$Launch.start_filetime_utc) {
        return $null
    }
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($Launch.pid)" -ErrorAction Stop
    if (!$cim -or !$cim.CommandLine -or
        !$cim.CommandLine.Contains($launcherPath) -or
        !$cim.CommandLine.Contains("-JobId $($Launch.job_id)") -or
        !$cim.CommandLine.Contains('-Action Worker')) {
        return $null
    }
    return $process
}

function Invoke-FpgaOwnerLockGuard([scriptblock]$Body) {
    $mutex = [Threading.Mutex]::new($false, 'Global\performance_soc_detached_fpga_owner')
    $held = $false
    try {
        try { $held = $mutex.WaitOne(5000) }
        catch [Threading.AbandonedMutexException] { $held = $true }
        if (!$held) { throw 'Timed out waiting for the FPGA owner lock guard' }
        & $Body
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

function Claim-FpgaOwnerLock([string]$Id) {
    Invoke-FpgaOwnerLockGuard {
        if (Test-Path -LiteralPath $fpgaLockPath) {
            $old = Get-Content -LiteralPath $fpgaLockPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $oldDirectory = Get-JobDirectory ([string]$old.job_id)
            $oldLaunchPath = Join-Path $oldDirectory 'launch.json'
            $oldReceiptPath = Join-Path $oldDirectory 'owner_receipt.json'
            $oldLaunch = if (Test-Path -LiteralPath $oldLaunchPath -PathType Leaf) {
                Get-Content -LiteralPath $oldLaunchPath -Raw -Encoding UTF8 | ConvertFrom-Json
            } else { $null }
            $oldReceipt = if (Test-Path -LiteralPath $oldReceiptPath -PathType Leaf) {
                Get-Content -LiteralPath $oldReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
            } else { $null }
            if ($old.schema -ne 1 -or (Get-VerifiedOwner $oldDirectory $oldLaunch) -or
                !(Test-OwnerReceipt $oldDirectory $oldLaunch $oldReceipt)) {
                throw "An FPGA owner lock is active or lacks a verified completion: $($old.job_id)"
            }
            Remove-Item -LiteralPath $fpgaLockPath -Force
        }
        $record = [ordered]@{
            schema=1; job_id=$Id; claimed_utc=[DateTime]::UtcNow.ToString('o')
        }
        $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 2) + "`n")
        $stream = [IO.File]::Open($fpgaLockPath, [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
        finally { $stream.Dispose() }
    }
}

function Release-FpgaOwnerLock([string]$Id) {
    Invoke-FpgaOwnerLockGuard {
        if (!(Test-Path -LiteralPath $fpgaLockPath -PathType Leaf)) { return }
        $record = Get-Content -LiteralPath $fpgaLockPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.schema -eq 1 -and $record.job_id -ceq $Id) {
            Remove-Item -LiteralPath $fpgaLockPath -Force
        }
    }
}

function Get-LaunchedOwnerStartFiletime([int]$OwnerPid, [string]$Id,
        [string]$ManifestHash, [string]$JobDirectory) {
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        foreach ($name in @('owner_identity.json','owner_receipt.json')) {
            $path = Join-Path $JobDirectory $name
            if (!(Test-Path -LiteralPath $path -PathType Leaf)) { continue }
            $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($name -ceq 'owner_identity.json') {
                if ($record.schema -eq 1 -and $record.job_id -ceq $Id -and
                    $record.pid -eq $OwnerPid -and
                    $record.launcher_sha256 -cne (Get-Sha256 $launcherPath)) { continue }
                if ($record.schema -eq 1 -and $record.job_id -ceq $Id -and
                    $record.pid -eq $OwnerPid -and $record.start_filetime_utc) {
                    return [long]$record.start_filetime_utc
                }
            } elseif ($record.schema -eq 1 -and $record.job_id -ceq $Id -and
                $record.owner_pid -eq $OwnerPid -and
                $record.manifest_sha256 -ceq $ManifestHash -and
                $record.owner_start_filetime_utc) {
                return [long]$record.owner_start_filetime_utc
            }
        }
        $process = Get-Process -Id $OwnerPid -ErrorAction SilentlyContinue
        if ($process) {
            try {
                $null = $process.Handle
                $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$OwnerPid" -ErrorAction Stop
                if ($cim -and $cim.CommandLine -and
                    $cim.CommandLine.Contains($launcherPath) -and
                    $cim.CommandLine.Contains("-JobId $Id") -and
                    $cim.CommandLine.Contains('-Action Worker')) {
                    return [long]$process.StartTime.ToUniversalTime().ToFileTimeUtc()
                }
            } catch { }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Detached owner PID/start identity was unavailable after launch: job=$Id pid=$OwnerPid"
}

function Quote-WindowsArgument([string]$Value) {
    $quoted = [Text.StringBuilder]::new()
    $null = $quoted.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            $null = $quoted.Append(('\' * ($slashes * 2 + 1)))
        } else {
            $null = $quoted.Append(('\' * $slashes))
        }
        $slashes = 0
        $null = $quoted.Append($character)
    }
    $null = $quoted.Append(('\' * ($slashes * 2)))
    $null = $quoted.Append('"')
    return $quoted.ToString()
}

function Invoke-BoundedOwnerTarget([string]$Target, [hashtable]$Arguments,
        [string]$StdoutPath, [string]$StderrPath, [int]$TimeoutSeconds) {
    if (!('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $root 'scripts/bounded_process.cs')
    }
    $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $tokens = @('-NoProfile','-NonInteractive','-WindowStyle','Hidden',
        '-ExecutionPolicy','Bypass','-File',$Target)
    foreach ($name in @($Arguments.Keys | Sort-Object)) {
        $value = $Arguments[$name]
        if ($value -is [bool]) {
            if ($value) { $tokens += '-' + $name }
        } else {
            $tokens += '-' + $name
            $tokens += [string]$value
        }
    }
    $argumentLine = (@($tokens | ForEach-Object { Quote-WindowsArgument ([string]$_) }) -join ' ')
    $exitCode = [CpuSimulation.BoundedProcess]::Run(
        $powershell, $argumentLine, $root, $StdoutPath, $StderrPath, $TimeoutSeconds)
    if ($exitCode -ne 0) { throw "Target script exited $exitCode; logs: $StdoutPath / $StderrPath" }
}

function Test-OwnerReceipt($JobDirectory, $Launch, $Receipt) {
    if (!$Receipt -or !$Launch -or
        $Receipt.schema -ne 1 -or $Receipt.job_id -cne $Launch.job_id -or
        $Receipt.owner_pid -ne $Launch.pid -or
        $Receipt.owner_start_filetime_utc -ne $Launch.start_filetime_utc -or
        $Receipt.manifest_sha256 -cne $Launch.manifest_sha256 -or
        $Receipt.status -notin @('OWNER_EXIT_ZERO','OWNER_FAILED') -or
        (($Receipt.status -ceq 'OWNER_EXIT_ZERO') -ne ($Receipt.exit_code -eq 0))) {
        return $false
    }
    if ((Get-Sha256 (Join-Path $JobDirectory 'manifest.json')) -cne $Launch.manifest_sha256) {
        return $false
    }
    foreach ($name in @('stdout','stderr')) {
        $path = Join-Path $JobDirectory "owner.$name.log"
        $recorded = $Receipt."${name}_sha256"
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            if (!$recorded -or (Get-Sha256 $path) -cne $recorded) { return $false }
        } elseif ($recorded) { return $false }
    }
    return $true
}

if ($Action -eq 'Worker') {
    Assert-OnlyParameters @('Action','JobId','ManifestSha256')
    $jobDirectory = Get-JobDirectory $JobId
    $receiptPath = Join-Path $jobDirectory 'owner_receipt.json'
    $stdoutPath = Join-Path $jobDirectory 'owner.stdout.log'
    $stderrPath = Join-Path $jobDirectory 'owner.stderr.log'
    $started = [DateTime]::UtcNow
    $result = [ordered]@{
        schema=1; label='DETACHED_OWNER_RECEIPT_NOT_RELEASE_PROOF'
        job_id=$JobId; owner_pid=$PID; started_utc=$started.ToString('o')
        owner_start_filetime_utc=[Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().ToFileTimeUtc()
        status='OWNER_INCOMPLETE'; exit_code=1; manifest_sha256=$ManifestSha256
        stdout_path=$stdoutPath; stderr_path=$stderrPath; error=''
    }
    try {
        if ($ManifestSha256 -cnotmatch $shaPattern) { throw 'Invalid expected manifest hash' }
        $manifestPath = Join-Path $jobDirectory 'manifest.json'
        if ((Get-Sha256 $manifestPath) -cne $ManifestSha256) { throw 'Manifest changed after launch' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.schema -ne 1 -or $manifest.job_id -cne $JobId -or
            $manifest.root -cne $root -or $manifest.launcher_path -cne $launcherPath -or
            $manifest.launcher_sha256 -cne (Get-Sha256 $launcherPath) -or
            $manifest.bounded_process_sha256 -cne (Get-Sha256 (Join-Path $root 'scripts/bounded_process.cs'))) {
            throw 'Detached owner manifest or launcher changed'
        }
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DetachedOwnerJobCheck { [DllImport("kernel32.dll", SetLastError=true)] public static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result); }'
        $insideJob = $false
        if (![DetachedOwnerJobCheck]::IsProcessInJob(
                [Diagnostics.Process]::GetCurrentProcess().Handle, [IntPtr]::Zero, [ref]$insideJob) -or $insideJob) {
            throw 'Detached owner still belongs to an outer Windows Job'
        }
        $result['kind'] = $manifest.kind
        $result['outer_job_membership'] = $false
        Write-JsonOnce (Join-Path $jobDirectory 'owner_identity.json') ([ordered]@{
            schema=1; job_id=$JobId; pid=$PID
            start_filetime_utc=$result.owner_start_filetime_utc
            launcher_sha256=$manifest.launcher_sha256
        })
        if ($manifest.kind -ceq 'Fixture') {
            $target = Join-Path $jobDirectory 'fixture_target.ps1'
            if (Test-Path -LiteralPath $target) { throw 'Fixture target already exists' }
            $fixtureScript = @'
param([int]$FixtureSeconds, [string]$FixtureMode, [string]$RepoRoot)
$ErrorActionPreference = 'Stop'
$DebugPreference = 'Continue'
Write-Output "FIXTURE_START pid=$PID"
Write-Warning 'FIXTURE_WARNING'
Write-Verbose 'FIXTURE_VERBOSE' -Verbose
Write-Information 'FIXTURE_INFORMATION' -InformationAction Continue
Write-Debug 'FIXTURE_DEBUG'
& $env:ComSpec /d /c 'echo BENIGN_NATIVE_STDERR 1>&2 & exit /b 0'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Add-Type -Path (Join-Path $RepoRoot 'scripts/bounded_process.cs')
$nestedOut = Join-Path $PSScriptRoot 'nested.stdout.log'
$nestedErr = Join-Path $PSScriptRoot 'nested.stderr.log'
$nestedExit = [CpuSimulation.BoundedProcess]::Run($env:ComSpec,
    '/d /c echo NESTED_JOB_PASS', $RepoRoot, $nestedOut, $nestedErr, 10)
if ($nestedExit -ne 0 -or
    !([IO.File]::ReadAllText($nestedOut)).Contains('NESTED_JOB_PASS')) {
    throw 'NESTED_JOB_FAILED'
}
Write-Output 'NESTED_JOB_PASS'
if ($FixtureMode -ceq 'NativeNonzero') {
    & $env:ComSpec /d /c 'echo EXPECTED_NATIVE_FAILURE 1>&2 & exit /b 7'
    exit $LASTEXITCODE
}
if ($FixtureMode -ceq 'PowerShellError') { throw 'EXPECTED_POWERSHELL_FAILURE' }
Start-Sleep -Seconds $FixtureSeconds
Write-Output 'FIXTURE_PASS'
'@
            [IO.File]::WriteAllText($target, $fixtureScript, [Text.UTF8Encoding]::new($false))
            $arguments = @{ FixtureSeconds=[int]$manifest.parameters.fixture_seconds
                FixtureMode=[string]$manifest.parameters.fixture_mode; RepoRoot=$root }
            $deadline = [int]$manifest.parameters.fixture_seconds + 30
        } else {
            $relative = if ($manifest.kind -ceq 'Fpga') {
                'scripts/build_fpga.ps1'
            } elseif ($manifest.kind -ceq 'LongCoreMark') {
                'scripts/run_coremark_production_sim.ps1'
            } else { throw "Unexpected job kind: $($manifest.kind)" }
            if ($manifest.target_relative_path -cne $relative) { throw 'Target script selector changed' }
            $target = Assert-ChildPath (Join-Path $root $relative) $root
            if ((Get-Sha256 $target) -cne $manifest.target_sha256) {
                throw 'Target script changed after launch'
            }
            $arguments = @{}
            if ($manifest.kind -ceq 'Fpga') {
                Write-JsonOnce (Join-Path $jobDirectory 'pds_process_guard_worker.json') (Assert-PdsProcessAvailability $root)
                $arguments.PdsTimeoutSeconds = [int]$manifest.parameters.pds_timeout_seconds
                $arguments.PdsShell = [string]$manifest.parameters.pds_shell
                $arguments.PythonPath = [string]$manifest.parameters.python_path
                $arguments.ToolchainRoot = [string]$manifest.parameters.toolchain_root
                $arguments.Distro = [string]$manifest.parameters.distro
                if ($manifest.parameters.campaign_budget) {
                    $arguments.CampaignBudget = [string]$manifest.parameters.campaign_budget
                    $arguments.AttemptPurpose = [string]$manifest.parameters.attempt_purpose
                }
            } else {
                $arguments.Kind = 'Long'
                $arguments.TimeoutSeconds = [int]$manifest.parameters.timeout_seconds
                $arguments.MaxCycles = [int]$manifest.parameters.max_cycles
                $arguments.CpuHz = [int]$manifest.parameters.cpu_hz
                $arguments.Iterations = [int]$manifest.parameters.iterations
                $arguments.BuildJobs = [int]$manifest.parameters.build_jobs
                $arguments.MsysRoot = [string]$manifest.parameters.msys_root
                $arguments.ToolchainRoot = [string]$manifest.parameters.toolchain_root
                $arguments.OutputDirectory = [string]$manifest.parameters.output_directory
                if ($manifest.parameters.release_evidence_directory) {
                    $arguments.ReleaseEvidenceDirectory = [string]$manifest.parameters.release_evidence_directory
                }
                if ($manifest.parameters.reuse_model_directory) {
                    $arguments.ReuseModel = $true
                    $arguments.ReuseModelDirectory = [string]$manifest.parameters.reuse_model_directory
                }
            }
            $deadline = if ($manifest.kind -ceq 'Fpga') {
                [Math]::Min(86400, 2 * [int]$manifest.parameters.pds_timeout_seconds + 3600)
            } else {
                [Math]::Min(86400, [int]$manifest.parameters.timeout_seconds + 3600)
            }
            if ($manifest.kind -ceq 'Fpga' -and $manifest.parameters.campaign_budget) {
                $campaign = Get-Content -LiteralPath $manifest.parameters.campaign_budget -Raw -Encoding UTF8 | ConvertFrom-Json
                $remaining = [int][Math]::Floor(([DateTimeOffset]::Parse($campaign.deadline) - [DateTimeOffset]::UtcNow).TotalSeconds)
                if ($remaining -le 0) { throw 'Campaign deadline elapsed before owner started' }
                $deadline = [Math]::Min($deadline, $remaining)
            }
        }
        Invoke-BoundedOwnerTarget $target $arguments $stdoutPath $stderrPath $deadline
        $result.status = 'OWNER_EXIT_ZERO'
        $result.exit_code = 0
    } catch {
        $result.status = 'OWNER_FAILED'
        $result.error = $_.Exception.GetBaseException().Message
        Add-Content -LiteralPath $stderrPath -Value $result.error -Encoding UTF8
    } finally {
        $result.completed_utc = [DateTime]::UtcNow.ToString('o')
        foreach ($name in @('stdout','stderr')) {
            $path = if ($name -eq 'stdout') { $stdoutPath } else { $stderrPath }
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $result["${name}_sha256"] = Get-Sha256 $path
            }
        }
        Write-JsonOnce $receiptPath $result
        if ($manifest -and $manifest.fpga_owner_lock -eq $true) {
            Release-FpgaOwnerLock $JobId
        }
    }
    exit ([int]$result.exit_code)
}

if ($Action -eq 'Status' -or $Action -eq 'Stop') {
    Assert-OnlyParameters @('Action','JobId')
    $jobDirectory = Get-JobDirectory $JobId
    $manifestPath = Join-Path $jobDirectory 'manifest.json'
    if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Unknown job: $JobId" }
    $launchPath = Join-Path $jobDirectory 'launch.json'
    $receiptPath = Join-Path $jobDirectory 'owner_receipt.json'
    $launch = if (Test-Path -LiteralPath $launchPath -PathType Leaf) {
        Get-Content -LiteralPath $launchPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else { $null }
    $receipt = if (Test-Path -LiteralPath $receiptPath -PathType Leaf) {
        Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else { $null }
    $owner = Get-VerifiedOwner $jobDirectory $launch
    if ($Action -eq 'Stop') {
        if (!$owner) { throw 'Owner PID/start time/command line cannot be verified; refusing to stop any process' }
        Write-JsonOnce (Join-Path $jobDirectory 'stop_request.json') ([ordered]@{
            schema=1; job_id=$JobId; pid=$owner.Id
            start_filetime_utc=$launch.start_filetime_utc
            requested_utc=[DateTime]::UtcNow.ToString('o')
        })
        if (!('DetachedOwnerTermination' -as [type])) {
            Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DetachedOwnerTermination { [DllImport("kernel32.dll", SetLastError=true)] public static extern bool TerminateProcess(IntPtr process, uint exitCode); }'
        }
        if (![DetachedOwnerTermination]::TerminateProcess($owner.Handle, 1)) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "Verified owner process handle could not be terminated: Win32=$errorCode"
        }
        if (!$owner.WaitForExit(5000)) { throw 'Verified owner did not exit within five seconds' }
        Release-FpgaOwnerLock $JobId
        Write-Output "STOP_REQUESTED job_id=$JobId owner_pid=$($owner.Id); the owner's kill-on-close Jobs stop bounded children"
        return
    }
    $receiptVerified = Test-OwnerReceipt $jobDirectory $launch $receipt
    $state = if ($receipt -and !$receiptVerified) { 'INVALID_OWNER_RECEIPT' }
        elseif ($receipt) { [string]$receipt.status }
        elseif ($owner) { 'OWNER_RUNNING' }
        elseif (Test-Path -LiteralPath (Join-Path $jobDirectory 'stop_request.json')) { 'STOPPED_OR_EXITED_AFTER_STOP_REQUEST_NO_RECEIPT' }
        else { 'INCOMPLETE_NO_RECEIPT' }
    [pscustomobject]@{
        job_id=$JobId; state=$state; owner_pid=if ($launch) { $launch.pid } else { $null }
        owner_verified_alive=[bool]$owner; receipt_verified=$receiptVerified
        exit_code=if ($receiptVerified) { $receipt.exit_code } else { $null }
        job_directory=$jobDirectory; receipt_path=if ($receipt) { $receiptPath } else { $null }
        stdout_path=Join-Path $jobDirectory 'owner.stdout.log'
        stderr_path=Join-Path $jobDirectory 'owner.stderr.log'
    } | ConvertTo-Json -Compress
    return
}

if ($Action -eq 'SelfTest') {
    Assert-OnlyParameters @('Action','FixtureSeconds','FixtureMode')
    $kind = 'Fixture'
    $parameters = [ordered]@{fixture_seconds=$FixtureSeconds; fixture_mode=$FixtureMode}
    $targetRelative = $null
    $targetHash = $null
} else {
    if ($Action -cne 'Start') { throw "Unexpected action: $Action" }
    if (!$Job) { throw '-Job Fpga, -Job LongCoreMark or -Job Fixture is required' }
    $kind = $Job
    if ($kind -ceq 'Fixture') {
        Assert-OnlyParameters @('Action','Job','FixtureSeconds','FixtureMode')
        $parameters = [ordered]@{fixture_seconds=$FixtureSeconds; fixture_mode=$FixtureMode}
        $targetRelative = $null
    } elseif ($kind -ceq 'Fpga') {
        Assert-OnlyParameters @('Action','Job','PdsTimeoutSeconds','PdsShell','PythonPath','ToolchainRoot','Distro','CampaignBudget','AttemptPurpose')
        if (!$PdsShell -or !$PythonPath -or !$ToolchainRoot) {
            throw 'Fpga requires explicit -PdsShell, -PythonPath and -ToolchainRoot for the detached environment'
        }
        . (Join-Path $PSScriptRoot 'build_pnr_budget.ps1')
        $CampaignBudget = Resolve-PnrCampaignBudget $root $CampaignBudget
        if ($CampaignBudget) {
            $CampaignBudget = Assert-ToolPath $CampaignBudget $false 'PnR campaign ledger'
            [void](Get-PnrCampaignSeconds $CampaignBudget $AttemptPurpose)
        }
        if ($Distro -cnotmatch '^[A-Za-z0-9_.-]+$') { throw 'Invalid WSL distro name' }
        $parameters = [ordered]@{
            pds_timeout_seconds=$PdsTimeoutSeconds
            pds_shell=Assert-ToolPath $PdsShell $false 'PDS shell'
            python_path=Assert-ToolPath $PythonPath $false 'Python'
            toolchain_root=Assert-ToolPath $ToolchainRoot $true 'RISC-V toolchain'
            distro=$Distro
            campaign_budget=$CampaignBudget
            attempt_purpose=$AttemptPurpose
        }
        if ([IO.Path]::GetFileName($parameters.pds_shell) -cne 'pds_shell.exe') {
            throw 'PDS executable must be pds_shell.exe'
        }
        $targetRelative = 'scripts/build_fpga.ps1'
    } else {
        Assert-OnlyParameters @('Action','Job','TimeoutSeconds','MaxCycles','CpuHz','Iterations',
            'BuildJobs','MsysRoot','ToolchainRoot','OutputDirectory','ReleaseEvidenceDirectory','ReuseModelDirectory')
        if (!$ToolchainRoot -or !$PSBoundParameters.ContainsKey('CpuHz') -or
            !$PSBoundParameters.ContainsKey('TimeoutSeconds') -or
            !$PSBoundParameters.ContainsKey('MaxCycles')) {
            throw 'LongCoreMark requires explicit -ToolchainRoot, -CpuHz, -TimeoutSeconds and -MaxCycles'
        }
        $idForOutput = [guid]::NewGuid().ToString('N')
        if (!$OutputDirectory) {
            $OutputDirectory = Join-Path $root "artifacts/selftest/production_coremark_long_$idForOutput"
        }
        $OutputDirectory = Assert-ChildPath $OutputDirectory (Join-Path $root 'artifacts/selftest')
        if (Test-Path -LiteralPath $OutputDirectory) { throw 'CoreMark output directory must be new' }
        if ($ReleaseEvidenceDirectory) {
            $ReleaseEvidenceDirectory = Assert-ChildPath $ReleaseEvidenceDirectory (Join-Path $root 'docs/validation')
            $validation = [IO.Path]::GetFullPath((Join-Path $root 'docs/validation')).TrimEnd('\')
            if (!(Split-Path -Parent $ReleaseEvidenceDirectory).Equals(
                    $validation, [StringComparison]::OrdinalIgnoreCase) -or
                (Test-Path -LiteralPath $ReleaseEvidenceDirectory)) {
                throw 'Release evidence must be a new direct child of docs/validation'
            }
        }
        if ($ReuseModelDirectory) {
            $ReuseModelDirectory = Assert-ChildPath $ReuseModelDirectory $root
            if (!(Test-Path -LiteralPath $ReuseModelDirectory -PathType Container)) {
                throw 'ReuseModelDirectory does not exist'
            }
        }
        $parameters = [ordered]@{
            timeout_seconds=$TimeoutSeconds; max_cycles=$MaxCycles; cpu_hz=$CpuHz
            iterations=$Iterations; build_jobs=$BuildJobs
            msys_root=Assert-ToolPath $MsysRoot $true 'MSYS root'
            toolchain_root=Assert-ToolPath $ToolchainRoot $true 'RISC-V toolchain'
            output_directory=$OutputDirectory
            release_evidence_directory=$ReleaseEvidenceDirectory
            reuse_model_directory=$ReuseModelDirectory
        }
        $targetRelative = 'scripts/run_coremark_production_sim.ps1'
    }
    $targetHash = if ($targetRelative) { Get-Sha256 (Join-Path $root $targetRelative) } else { $null }
}

New-Item -ItemType Directory -Path $storeRoot -Force | Out-Null
$newId = [guid]::NewGuid().ToString('N')
$jobDirectory = Get-JobDirectory $newId
$claimOwnerLock = $kind -ceq 'Fpga' -or ($Action -ceq 'Start' -and $kind -ceq 'Fixture')
$claimed = $false
$workerCreated = $false
try {
    if ($claimOwnerLock) { Claim-FpgaOwnerLock $newId; $claimed = $true }
    New-Item -ItemType Directory -Path $jobDirectory -ErrorAction Stop | Out-Null
    $manifestPath = Join-Path $jobDirectory 'manifest.json'
    Write-JsonOnce $manifestPath ([ordered]@{
        schema=1; label=if ($kind -eq 'Fixture') { 'FIXTURE_ONLY_NOT_RELEASE' } else { 'DETACHED_OWNER_ONLY' }
        job_id=$newId; kind=$kind; root=$root; launcher_path=$launcherPath
        launcher_sha256=Get-Sha256 $launcherPath
        bounded_process_sha256=Get-Sha256 (Join-Path $root 'scripts/bounded_process.cs')
        target_relative_path=$targetRelative; target_sha256=$targetHash
        fpga_owner_lock=$claimOwnerLock
        parameters=$parameters; created_utc=[DateTime]::UtcNow.ToString('o')
    })
    $manifestHash = Get-Sha256 $manifestPath
    if ($kind -ceq 'Fpga') {
        Write-JsonOnce (Join-Path $jobDirectory 'pds_process_guard_start.json') (Assert-PdsProcessAvailability $root)
    }
    $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $commandLine = '"' + $powershell + '" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
        $launcherPath + '" -Action Worker -JobId ' + $newId + ' -ManifestSha256 ' + $manifestHash
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine=$commandLine; CurrentDirectory=$root
    }
    if ($created.ReturnValue -ne 0 -or !$created.ProcessId) {
        Write-JsonOnce (Join-Path $jobDirectory 'launch_error.json') ([ordered]@{
            schema=1; job_id=$newId; return_value=$created.ReturnValue
            attempted_utc=[DateTime]::UtcNow.ToString('o')
        })
        throw "Win32_Process.Create failed with return value $($created.ReturnValue); job=$newId"
    }
    $workerCreated = $true
    $ownerStartFiletime = Get-LaunchedOwnerStartFiletime ([int]$created.ProcessId) $newId $manifestHash $jobDirectory
    Write-JsonOnce (Join-Path $jobDirectory 'launch.json') ([ordered]@{
        schema=1; job_id=$newId; pid=[int]$created.ProcessId
        start_filetime_utc=$ownerStartFiletime
        launcher_sha256=Get-Sha256 $launcherPath; manifest_sha256=$manifestHash
        launched_utc=[DateTime]::UtcNow.ToString('o')
    })
    Write-Output "DETACHED_OWNER_STARTED job_id=$newId kind=$kind pid=$($created.ProcessId) root=$jobDirectory"
    Write-Output "Status: & '$launcherPath' -Action Status -JobId $newId"
    Write-Output "Stop:   & '$launcherPath' -Action Stop -JobId $newId"
    Write-Output 'The target has its own bounded Windows Jobs. No release result is valid until owner_receipt.json and the target native evidence pass.'
} catch {
    if ($claimed -and !$workerCreated) { Release-FpgaOwnerLock $newId }
    throw
}
