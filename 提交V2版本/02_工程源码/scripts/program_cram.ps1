[CmdletBinding()]
param(
    [switch]$Program,
    [switch]$ScanOnly,
    [switch]$DryRun,
    [string]$PdsRoot = '',
    [string]$SbitPath,
    [switch]$AllowExternalSbit,
    [ValidateSet('Project', 'CPU80Approved', 'CPU60FunctionalTrial', 'MainP3Published', 'PublishedE42', 'Main70Candidate', 'Main75Candidate')]
    [string]$AuditProfile = 'Project',
    [string]$TrialDirectory,
    [ValidateRange(1, 65535)]
    [int]$JtagServerPort = 65420,
    [string]$LogPath,
    [ValidateRange(10, 600)][int]$OperationTimeoutSeconds = 120,
    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'

function Assert-SafeConfigurationTcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$AllowedCommands
    )

    $text = [IO.File]::ReadAllText($Path)
    $forbidden = '(?i)\b(?:flash|erase|svf|readback|efuse|key_file|security|otp)\b'
    if ([Text.RegularExpressions.Regex]::IsMatch($text, $forbidden)) {
        throw "Unsafe configuration operation in $Path. Flash, erase, SVF, readback, eFuse, key, security, and OTP operations are not supported."
    }

    $commands = [Text.RegularExpressions.Regex]::Matches(
        $text,
        '(?i)\b(cfg_[a-z0-9_]+)\b'
    ) | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    foreach ($command in $commands) {
        if ($AllowedCommands -notcontains $command) {
            throw "Unsupported configuration command '$command' in $Path. Only volatile CRAM scan/program commands are allowed."
        }
    }
}

function Assert-ExactConfigurationFlow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedLines
    )

    $actualLines = @(Get-Content -LiteralPath $Path | ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and !$_.StartsWith('#') })
    if ($actualLines.Count -ne $ExpectedLines.Count) {
        throw "Unexpected Tcl flow length in $Path; refusing hardware access."
    }
    for ($index = 0; $index -lt $ExpectedLines.Count; $index++) {
        if ($actualLines[$index] -cne $ExpectedLines[$index]) {
            throw "Unexpected Tcl operation at line $($index + 1) in $Path; refusing hardware access."
        }
    }
}

function Assert-Pg2l100hScan {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [string]$Source
    )

    if (!$Text.Contains('Executing : cfg_scan_chain successfully.')) {
        throw "PDS did not report a successful JTAG scan in $Source"
    }
    if (!$Text.Contains('Executing : cfg_read_device_property -mode 0 -device_index 0 successfully.')) {
        throw "PDS did not identify device index 0 in $Source"
    }

    $deviceNames = [Text.RegularExpressions.Regex]::Matches(
        $Text,
        '(?im)^\s*PG2L100H\s*$'
    )
    $deviceStatuses = [Text.RegularExpressions.Regex]::Matches(
        $Text,
        '(?im)^\s*This device configure situation \(done bit\):\s*[01]\s*$'
    )
    $expectedIds = [Text.RegularExpressions.Regex]::Matches(
        $Text,
        '(?im)^\s*The ID value is:\s*0x00602899\s*$'
    )
    if ($deviceNames.Count -ne 1 -or
        $deviceStatuses.Count -ne 1 -or
        $expectedIds.Count -ne 1) {
        throw "Unsafe JTAG chain in $Source. Expected exactly one device at index 0: PG2L100H (ID 0x00602899); found PG2L100H=$($deviceNames.Count), devices=$($deviceStatuses.Count), expected_ID=$($expectedIds.Count)."
    }
}

function Invoke-ConfigurationShell {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigShell,
        [Parameter(Mandatory = $true)]
        [string]$TclPath,
        [Parameter(Mandatory = $true)]
        [string]$TclArguments,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    if (!('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
    }
    $arguments = '-file "' + $TclPath + '" -args "' + $TclArguments +
        '" -work_dir "' + $WorkingDirectory + '" -report_dir "' +
        (Split-Path -Parent $OutputPath) + '"'
    $errorPath = $OutputPath + '.stderr.txt'
    $exitCode = [CpuSimulation.BoundedProcess]::Run($ConfigShell, $arguments,
        $WorkingDirectory, $OutputPath, $errorPath, $OperationTimeoutSeconds)
    $output = [IO.File]::ReadAllText($OutputPath)
    $errors = [IO.File]::ReadAllText($errorPath)
    Write-Host $output
    if ($errors) { Write-Host $errors }
    if ($exitCode -ne 0) {
        throw "PDS configuration shell exited with code $exitCode; inspect $OutputPath"
    }
    if ($output -match '(?m)^\s*E:\s' -or $errors -match '(?m)^\s*E:\s') {
        throw "PDS configuration shell reported an error despite exit 0; inspect $OutputPath"
    }
    return $output
}

function Assert-ProjectBitstreamEvidence {
    param([string]$Root, [string]$Bitstream, [string]$ExpectedHash)

    if ($AuditProfile -eq 'Main75Candidate') {
        if (!$TrialDirectory -or $ExpectedHash -cne 'd2ab7f6dfdbfdb7def8fba6f872ba3ce302ee1b914bee093477060ff97939675') {
            throw 'Main75Candidate requires its exact native result directory and bitstream.'
        }
        $text = & G:/py/ana/python.exe -B (Join-Path $PSScriptRoot 'audit_main75_candidate.py') --root $Root --native-result (Join-Path $TrialDirectory 'native-result.json') --bitstream $Bitstream
        if ($LASTEXITCODE -ne 0) { throw 'CPU75 native identity audit failed' }
        $identity = $text | ConvertFrom-Json
        if ($identity.status -cne 'EXACT_MAIN75_NATIVE_ROM_STA_INPUTS_OUTPUTS_PASS_NOT_FORMAL_RELEASE' -or !$identity.formal_sta_pass -or !$identity.native_preflight_complete -or $identity.formal_release) { throw 'CPU75 candidate audit scope mismatch' }
        $script:Main75Identity = $identity
        Write-Host 'MAIN75_CANDIDATE_AUDIT_PASS inputs=517 reports=46 outputs=49 STA_rows=116 skew_rows=20 formal_release=false'
        return
    }
    if ($AuditProfile -eq 'Main70Candidate') {
        if (!$TrialDirectory -or $ExpectedHash -cne '24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02') {
            throw 'Main70Candidate requires its exact native result directory and bitstream.'
        }
        $text = & G:/py/ana/python.exe -B (Join-Path $PSScriptRoot 'audit_main70_candidate.py') --root $Root --native-result (Join-Path $TrialDirectory 'result.json') --bitstream $Bitstream
        if ($LASTEXITCODE -ne 0) { throw 'CPU70 native identity audit failed' }
        $identity = $text | ConvertFrom-Json
        if ($identity.status -cne 'EXACT_MAIN70_NATIVE_ROM_STA_INPUTS_OUTPUTS_PASS_NOT_FORMAL_RELEASE' -or !$identity.formal_sta_pass -or !$identity.native_preflight_complete -or $identity.formal_release) { throw 'CPU70 candidate audit scope mismatch' }
        $script:Main70Identity = $identity
        Write-Host 'MAIN70_CANDIDATE_AUDIT_PASS inputs=513 reports=42 outputs=47 STA_rows=116 skew_rows=20 formal_release=false'
        return
    }
    if ($AuditProfile -eq 'PublishedE42') {
        if ($ExpectedHash -cne 'e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b') {
            throw 'PublishedE42 accepts only the exact published e42 image.'
        }
        foreach ($binding in @(
            @('audit_published_e42.ps1','d5ca8bbd1e7695967095723a32c1e70cbacedd1f2a880451fa2d4a1a11bb9fd4'),
            @('check_published_e42.py','522c7cee41d0f82cd9d669defb39f277652884403945cb30e693d682f99a5189')
        )) {
            if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $binding[0]) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $binding[1]) {
                throw 'Published e42 audit/checker differs from the reviewed adapter.'
            }
        }
        $publishedText=& (Join-Path $PSScriptRoot 'audit_published_e42.ps1') -Root $Root -Bitstream $Bitstream
        $published=$publishedText|ConvertFrom-Json
        if ($published.status -cne 'EXACT_PUBLISHED_E42_IDENTITY_PASS_NOT_FORMAL_RELEASE' -or
            $published.native_input_hashes -ne 498 -or $published.live_native_inputs -ne 491 -or
            $published.archived_build_helpers -ne 7 -or !$published.upstream_sta_pass -or
            $published.native_database_replay_complete -or $published.formal_release) {
            throw 'Published e42 audit scope is incomplete or misleading.'
        }
        $script:PublishedE42Identity=$published
        Write-Host 'PUBLISHED_E42_AUDIT_PASS native_inputs=498 live=491 archived_helpers=7 raw_STA_rows=116 skew_rows=20 original_database_replay=false formal_release=false'
        return
    }
    if ($AuditProfile -eq 'MainP3Published') {
        if ($ExpectedHash -cne '6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd') {
            throw 'MainP3Published accepts only the exact published main P3 image.'
        }
        foreach ($binding in @(
            @('audit_main_p3_published.ps1','4e36f037d6c3c12e50031ebc5bb97bbb3aec65f3056c4226426afc495cfbe8f5'),
            @('check_main_p3_published.py','f2bc8d6fc14cd8b6b5449451c407cf317cf770cc85967f7d4abaa0deb19dbbe7')
        )) {
            if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $binding[0]) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $binding[1]) {
                throw 'Published P3 audit/checker differs from the reviewed adapter.'
            }
        }
        $publishedText=& (Join-Path $PSScriptRoot 'audit_main_p3_published.ps1') -Root $Root -Bitstream $Bitstream
        $published=$publishedText|ConvertFrom-Json
        if ($published.status -cne 'EXACT_MAIN_P3_PUBLISHED_IDENTITY_PASS_NOT_FORMAL_RELEASE' -or
            $published.frozen_inputs -ne 495 -or !$published.upstream_sta_pass -or
            $published.native_database_replay_complete -or $published.formal_release) {
            throw 'Published P3 audit scope is incomplete or misleading.'
        }
        $script:MainP3PublishedIdentity=$published
        Write-Host 'MAIN_P3_PUBLISHED_AUDIT_PASS inputs=495 raw_STA_rows=116 skew_rows=20 original_database_replay=false formal_release=false'
        return
    }
    if ($AuditProfile -eq 'CPU60FunctionalTrial') {
        if (!$TrialDirectory -or $ExpectedHash -cne '9ba02f105d6168e9445e9a15e2f7a1093d885229deae9e268994acdbe29f5ea1') {
            throw 'CPU60FunctionalTrial requires the exact authorized image and explicit trial material directory.'
        }
        $trialText = & (Join-Path $PSScriptRoot 'audit_cpu60_functional_trial.ps1') -Root $Root -TrialDirectory $TrialDirectory -Bitstream $Bitstream
        $trial = $trialText | ConvertFrom-Json
        if ($trial.status -cne 'EXACT_CPU60_FUNCTIONAL_TRIAL_IDENTITY_PASS_NOT_RELEASE' -or $trial.formal_sta_pass -or $trial.native_preflight_complete) {
            throw 'CPU60 functional trial must retain its disclosed STA failure and missing native records.'
        }
        $script:Cpu60TrialIdentity = $trial
        Write-Host 'CPU60_FUNCTIONAL_TRIAL_AUDIT_PASS exact_inputs=491 formal_sta_pass=false native_preflight_complete=false'
        return
    }
    # The project audit includes release/device/final STA checks as well as
    # the complete current CPU/ROM/input snapshot and output hashes.
    $evidence = [IO.File]::ReadAllText((Join-Path $Root 'artifacts/build_evidence.json')) | ConvertFrom-Json
    $auditName = 'audit_project.ps1'
    if ($AuditProfile -eq 'CPU80Approved') {
        if ($evidence.run_id -cne '44aa982f752c4b7d91accea60292735f' -or
            $ExpectedHash -cne '30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1') {
            throw 'CPU80Approved audit requires the exact CPU80 run and bitstream.'
        }
        # The upstream adapter preserves the frozen audit and all native input,
        # CPU/ROM/STA/output checks, permitting only two exact inherited files.
        $auditName = 'audit_cpu80_approved.ps1'
        $adapterHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $auditName) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($adapterHash -cne '5945b6622f0824ddd937a95f6b09982af28e9cf6aa2f7086a0ca66481597a128') {
            throw 'CPU80Approved audit adapter differs from the imported upstream adapter.'
        }
    }
    & (Join-Path $PSScriptRoot $auditName) -Root $Root | ForEach-Object { Write-Host $_ }
    $recordedHash = $evidence.outputs.'artifacts/soc_top.sbit'
    $actualHash = (Get-FileHash -LiteralPath $Bitstream -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($recordedHash -cne $ExpectedHash -or $actualHash -cne $ExpectedHash) {
        throw 'Selected .sbit does not match the current audited FPGA build evidence.'
    }
}

function Assert-NewConfigurationEvidencePaths {
    param([string[]]$Paths)
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($path in $Paths) {
        $full = [IO.Path]::GetFullPath($path)
        if (!$seen.Add($full) -or (Test-Path -LiteralPath $full)) {
            throw "Configuration evidence path exists or collides: $full"
        }
        $cursor = Split-Path -Parent $full
        if (!(Test-Path -LiteralPath $cursor -PathType Container)) { throw 'Configuration evidence parent must exist' }
        while ($cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Configuration evidence path follows a link'
            }
            $cursor = Split-Path -Parent $cursor
        }
    }
}

function Get-ProgramProjectIdentity {
    param([string]$Root)
    if ($AuditProfile -eq 'Main75Candidate') {
        $identity=[ordered]@{}
        foreach($p in $script:Main75Identity.PSObject.Properties){$identity[$p.Name]=$p.Value}
        return $identity
    }
    if ($AuditProfile -eq 'Main70Candidate') {
        $identity=[ordered]@{}
        foreach($p in $script:Main70Identity.PSObject.Properties){$identity[$p.Name]=$p.Value}
        return $identity
    }
    if ($AuditProfile -eq 'PublishedE42') {
        $identity=[ordered]@{}
        foreach ($name in @('source_ref','hardware_origin_commit','run_id','bitstream_sha256',
            'firmware_binary_sha256','cpu_rtl_sha256','cpu_source_manifest_sha256',
            'pds_snapshot_sha256','pds_build_evidence_sha256','native_input_hashes',
            'live_native_inputs','archived_build_helpers','audit_script_sha256','identity_checker_sha256')) {
            $identity[$name]=$script:PublishedE42Identity.$name
        }
        $identity.pds_snapshot_run_id=$script:PublishedE42Identity.run_id
        $identity.published_source_ref=$script:PublishedE42Identity.source_ref
        $identity.original_database_replay_complete=$false
        $identity.formal_release=$false
        $identity.raw_sta_summary_rows=116
        $identity.raw_sta_max_skew_rows=20
        return $identity
    }
    if ($AuditProfile -eq 'CPU60FunctionalTrial') {
        $identity = [ordered]@{}
        foreach ($name in @('source_ref','run_id','bitstream_sha256','firmware_binary_sha256','cpu_rtl_sha256','cpu_source_manifest_sha256','pds_snapshot_sha256','authorization_sha256','audit_script_sha256','identity_checker_sha256','formal_sta_pass','native_preflight_complete')) {
            $identity[$name] = $script:Cpu60TrialIdentity.$name
        }
        return $identity
    }
    $identity = [ordered]@{}
    foreach ($binding in @(
        @('firmware_binary_sha256','artifacts/bootloader.bin'),
        @('cpu_rtl_sha256','rtl/cpu/CoreTop.sv'),
        @('cpu_source_manifest_sha256','rtl/cpu/source.json'),
        @('pds_snapshot_sha256','artifacts/build_snapshot.json'),
        @('pds_build_evidence_sha256','artifacts/build_evidence.json')
    )) {
        $identity[$binding[0]] = (Get-FileHash -LiteralPath (Join-Path $Root $binding[1]) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $identity.pds_snapshot_run_id = ([IO.File]::ReadAllText((Join-Path $Root 'artifacts/build_evidence.json')) | ConvertFrom-Json).run_id
    if ($AuditProfile -eq 'MainP3Published') {
        $identity.published_source_ref=$script:MainP3PublishedIdentity.source_ref
        $identity.original_database_replay_complete=$false
        $identity.formal_release=$false
        $identity.raw_sta_summary_rows=116
        $identity.raw_sta_max_skew_rows=20
    }
    return $identity
}

$selectedModes = @($Program.IsPresent, $ScanOnly.IsPresent, $DryRun.IsPresent) |
    Where-Object { $_ }
if ($selectedModes.Count -gt 1) {
    throw 'Choose only one operation: -Program, -ScanOnly, or -DryRun.'
}
$mode = if ($Program) { 'Program' } elseif ($ScanOnly) { 'ScanOnly' } else { 'DryRun' }

$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$artifactsRoot = [IO.Path]::GetFullPath((Join-Path $root 'artifacts'))
$explicitSbitPath = $PSBoundParameters.ContainsKey('SbitPath') -and ![string]::IsNullOrWhiteSpace($SbitPath)
if (!$SbitPath) { $SbitPath = Join-Path $artifactsRoot 'soc_top.sbit' }
if (!$LogPath) {
    $logName = if ($mode -eq 'ScanOnly') { 'board_scan_chain.log' } else { 'board_program_cram.log' }
    $LogPath = Join-Path $artifactsRoot $logName
}

if ([string]::IsNullOrWhiteSpace($PdsRoot)) {
    $pdsCandidates = @()
    if ($env:PDS_ROOT) { $pdsCandidates += $env:PDS_ROOT }
    $pdsCandidates += @(
        'G:\fpga\PDS_2022.2-SP6.4',
        'D:\LJL\WORK\pango\PDS_2022.2-SP6.4'
    )
    $PdsRoot = $pdsCandidates | Where-Object {
        $candidateShell = [IO.Path]::Combine($_, 'bin', 'cdt_cfg_shell.exe')
        Test-Path -LiteralPath $candidateShell -PathType Leaf
    } | Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($PdsRoot)) {
    throw 'Missing PDS. Pass -PdsRoot or set PDS_ROOT.'
}
$PdsRoot = [IO.Path]::GetFullPath($PdsRoot)
$LogPath = [IO.Path]::GetFullPath($LogPath)
$jtagServer = Join-Path $PdsRoot 'bin\cdt_js.exe'
$configShell = Join-Path $PdsRoot 'bin\cdt_cfg_shell.exe'
$programTcl = Join-Path $PSScriptRoot 'pds_program_cram.tcl'
$scanTcl = Join-Path $PSScriptRoot 'pds_scan_chain.tcl'

foreach ($path in @($jtagServer, $configShell, $programTcl, $scanTcl)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
if (!(Test-Path -LiteralPath (Split-Path -Parent $LogPath) -PathType Container)) {
    throw "Log directory does not exist: $(Split-Path -Parent $LogPath)"
}
if ([IO.Path]::GetExtension($LogPath) -ine '.log') {
    throw "Configuration output must use a .log path: $LogPath"
}
if ($mode -ne 'DryRun' -and (Test-Path -LiteralPath $LogPath)) {
    throw "Use a new operation log; existing evidence is preserved: $LogPath"
}
if (Test-Path -LiteralPath $LogPath) {
    $logItem = Get-Item -LiteralPath $LogPath -Force
    if ($logItem.PSIsContainer -or
        ($logItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing a directory, symbolic link, or reparse-point log path: $LogPath"
    }
}

Assert-SafeConfigurationTcl -Path $scanTcl -AllowedCommands @(
    'cfg_set_tcl_break', 'cfg_connect', 'cfg_scan_chain',
    'cfg_read_device_property', 'cfg_disconnect', 'cfg_close'
)
Assert-SafeConfigurationTcl -Path $programTcl -AllowedCommands @(
    'cfg_set_tcl_break', 'cfg_connect', 'cfg_scan_chain',
    'cfg_read_device_property', 'cfg_assign_file', 'cfg_program',
    'cfg_disconnect', 'cfg_close'
)
Assert-ExactConfigurationFlow -Path $scanTcl -ExpectedLines @(
    'cfg_set_tcl_break -flag true',
    'cfg_connect -ip 127.0.0.1 -port %s',
    'cfg_scan_chain',
    'after 1000',
    'cfg_read_device_property -mode 0 -device_index 0',
    'cfg_read_device_property -mode 3 -device_index 0',
    'cfg_disconnect',
    'cfg_close'
)
Assert-ExactConfigurationFlow -Path $programTcl -ExpectedLines @(
    'cfg_set_tcl_break -flag true',
    'cfg_connect -ip 127.0.0.1 -port %s',
    'cfg_scan_chain',
    'after 1000',
    'cfg_read_device_property -mode 0 -device_index 0',
    'cfg_assign_file -file %s -device_index 0',
    'cfg_program -device_index 0',
    'cfg_read_device_property -mode 3 -device_index 0',
    'cfg_disconnect',
    'cfg_close'
)

$resolvedSbit = $null
$sbitHash = $null
$requiresProjectEvidence = $false
if ($mode -ne 'ScanOnly') {
    if (!(Test-Path -LiteralPath $SbitPath -PathType Leaf)) {
        throw "Missing required .sbit file: $SbitPath"
    }
    $sbitItem = Get-Item -LiteralPath $SbitPath -Force
    if ($sbitItem.Extension -ine '.sbit') {
        throw "Only volatile CRAM .sbit files are accepted. Flash, erase, SVF, and readback operations are rejected: $($sbitItem.FullName)"
    }
    if (($sbitItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing a symbolic link or reparse-point bitstream: $($sbitItem.FullName)"
    }
    $resolvedSbit = [IO.Path]::GetFullPath($sbitItem.FullName)
    $pdsSafePath = $resolvedSbit.Replace('\', '/')
    if ($pdsSafePath -notmatch '^[A-Za-z]:/[A-Za-z0-9._/-]+$') {
        throw "Bitstream path contains characters that are unsafe for PDS Tcl argument conversion: $resolvedSbit"
    }
    if ($resolvedSbit.Equals($LogPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The bitstream and configuration log paths must be different.'
    }
    $artifactPrefix = $artifactsRoot.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    if (!$AllowExternalSbit -and
        !$resolvedSbit.StartsWith($artifactPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Bitstream must be an existing .sbit under $artifactsRoot. Use -AllowExternalSbit only after separately verifying an external CRAM image."
    }
    $sbitHash = (Get-FileHash -LiteralPath $resolvedSbit -Algorithm SHA256).Hash.ToLowerInvariant()
    $requiresProjectEvidence = $resolvedSbit.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
    if ($requiresProjectEvidence) {
        # -AllowExternalSbit never bypasses the default or other in-repo image.
        Assert-ProjectBitstreamEvidence -Root $root -Bitstream $resolvedSbit -ExpectedHash $sbitHash
    } elseif (!$explicitSbitPath -or !$AllowExternalSbit) {
        throw 'An external image requires an explicit -SbitPath together with -AllowExternalSbit.'
    } elseif ($AuditProfile -ne 'Project') {
        throw 'Special audit profiles cannot be used for an external image.'
    }
}

Write-Host "CRAM operation: $mode"
Write-Host "Audit profile: $AuditProfile"
Write-Host "PDS root: $PdsRoot"
Write-Host 'Allowed hardware action: volatile FPGA CRAM scan/program only'
Write-Host 'Rejected hardware actions: Flash, erase, SVF, readback, eFuse, key, security, and OTP'
if ($resolvedSbit) {
    Write-Host "Bitstream: $resolvedSbit"
    Write-Host "SHA-256: $sbitHash"
    if ($requiresProjectEvidence) {
        if ($AuditProfile -eq 'CPU60FunctionalTrial') {
            Write-Host 'Image evidence: exact archived CPU60 trial source/ROM/491 inputs; STA failed and four original native records missing; functional trial only.'
        } elseif ($AuditProfile -eq 'MainP3Published') {
            Write-Host 'Image evidence: exact published main P3/495 inputs/portable original evidence/raw STA; original database replay incomplete; functional CRAM assignment, not formal release.'
        } elseif ($AuditProfile -eq 'PublishedE42') {
            Write-Host 'Image evidence: exact published e42/498 original inputs (491 live,7 archived helpers)/original STA; original database replay incomplete; functional CRAM assignment, not formal release.'
        } else { Write-Host 'Image evidence: current project snapshot, CPU/ROM, final STA and selected bitstream match.' }
    } else {
        Write-Host 'External image: explicitly supplied; no current project CPU/ROM/STA match is asserted.'
    }
}

if ($mode -eq 'DryRun') {
    Write-Host 'DRY_RUN_PASS: no JTAG server was started and no hardware was accessed.'
    Write-Host 'Future program command:'
    if ($explicitSbitPath) {
        $externalArgument = if ($AllowExternalSbit) { ' -AllowExternalSbit' } else { '' }
        $trialArgument = if ($AuditProfile -in @('CPU60FunctionalTrial', 'Main75Candidate')) { " -TrialDirectory '$TrialDirectory'" } else { '' }
        Write-Host "  .\scripts\program_cram.ps1 -Program -SbitPath '$resolvedSbit'$externalArgument -AuditProfile $AuditProfile$trialArgument"
    } else {
        Write-Host "  .\scripts\program_cram.ps1 -Program -AuditProfile $AuditProfile"
    }
    return
}

$serverProcess = $null
$startedServer = $false
$operationStarted = [DateTime]::UtcNow.ToString('o')
$programEvidence = $null
$preflightLog = Join-Path (Split-Path -Parent $LogPath) `
    (([IO.Path]::GetFileNameWithoutExtension($LogPath)) + '.preflight.log')
if ($mode -eq 'Program') {
    if (!$EvidencePath) { $EvidencePath = $LogPath + '.json' }
    $EvidencePath = [IO.Path]::GetFullPath($EvidencePath)
    if (Test-Path -LiteralPath $EvidencePath) { throw "Program evidence already exists: $EvidencePath" }
    if (!(Test-Path -LiteralPath (Split-Path -Parent $EvidencePath) -PathType Container)) {
        throw 'Program evidence parent must exist'
    }
    $programEvidence = [ordered]@{
        schema_version = 1; evidence_kind = 'volatile_cram_program'; status = 'INCOMPLETE'
        started_utc = $operationStarted; completed_utc = $null
        operation = 'CRAM'; device = $null; device_id = $null
        device_count = $null; device_index = $null
        bitstream_sha256 = $sbitHash
        audit_profile = $AuditProfile
        program_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        audit_script_sha256 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $(if ($AuditProfile -eq 'Main75Candidate') {'audit_main75_candidate.py'} elseif ($AuditProfile -eq 'Main70Candidate') {'audit_main70_candidate.py'} elseif ($AuditProfile -eq 'CPU80Approved') {'audit_cpu80_approved.ps1'} elseif ($AuditProfile -eq 'CPU60FunctionalTrial') {'audit_cpu60_functional_trial.ps1'} elseif ($AuditProfile -eq 'MainP3Published') {'audit_main_p3_published.ps1'} elseif ($AuditProfile -eq 'PublishedE42') {'audit_published_e42.ps1'} else {'audit_project.ps1'})) -Algorithm SHA256).Hash.ToLowerInvariant()
        assigned_bitstream_path = $pdsSafePath
        provenance = 'Observed scan, file assignment, and successful volatile CRAM programming; no configuration readback.'
    }
}
$evidencePaths = @($LogPath, ($LogPath + '.stderr.txt'))
if ($mode -eq 'Program') { $evidencePaths += $preflightLog, ($preflightLog + '.stderr.txt'), $EvidencePath }
Assert-NewConfigurationEvidencePaths $evidencePaths
try {
    $listeners = @(Get-NetTCPConnection -LocalPort $JtagServerPort `
        -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $ownerIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        if ($ownerIds.Count -ne 1) {
            throw "More than one process is listening on JTAG server port $JtagServerPort"
        }
        $owner = Get-Process -Id $ownerIds[0] -ErrorAction Stop
        $ownerPath = $owner.Path
        if (!$ownerPath -or
            ![IO.Path]::GetFullPath($ownerPath).Equals(
                [IO.Path]::GetFullPath($jtagServer),
                [StringComparison]::OrdinalIgnoreCase
            )) {
            throw "Port $JtagServerPort is owned by '$ownerPath', not the configured PDS JTAG server '$jtagServer'"
        }
    } else {
        $serverProcess = Start-Process -FilePath $jtagServer -ArgumentList @(
            '-port', "$JtagServerPort", '-work_dir', $root
        ) -WindowStyle Hidden -PassThru
        $startedServer = $true
        $deadline = (Get-Date).AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 200
            $listeners = @(Get-NetTCPConnection -LocalPort $JtagServerPort `
                -State Listen -ErrorAction SilentlyContinue)
        } while ($listeners.Count -eq 0 -and (Get-Date) -lt $deadline)
        if ($listeners.Count -eq 0) { throw 'PDS JTAG Server did not start' }
    }

    if ($mode -eq 'ScanOnly') {
        $scanText = Invoke-ConfigurationShell -ConfigShell $configShell `
            -TclPath $scanTcl -TclArguments "{ $JtagServerPort }" `
            -WorkingDirectory $root -OutputPath $LogPath
        Assert-Pg2l100hScan -Text $scanText -Source $LogPath
        Write-Host "SCAN_ONLY_PASS: exactly one PG2L100H (index 0, ID 0x00602899); log: $LogPath"
        return
    }

    # A separate read-only preflight is the authorization gate. The following
    # program session scans again and keeps connect/scan/assign/program/disconnect
    # together in one cfg-shell process.
    $scanText = Invoke-ConfigurationShell -ConfigShell $configShell `
        -TclPath $scanTcl -TclArguments "{ $JtagServerPort }" `
        -WorkingDirectory $root -OutputPath $preflightLog
    Assert-Pg2l100hScan -Text $scanText -Source $preflightLog

    $currentHash = (Get-FileHash -LiteralPath $resolvedSbit -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($currentHash -ne $sbitHash) {
        throw 'The .sbit changed after validation; refusing to program it.'
    }
    if ($requiresProjectEvidence) {
        Assert-ProjectBitstreamEvidence -Root $root -Bitstream $resolvedSbit -ExpectedHash $sbitHash
        $identityBeforeProgram = Get-ProgramProjectIdentity $root
    }

    $pdsPath = $pdsSafePath
    $programText = Invoke-ConfigurationShell -ConfigShell $configShell `
        -TclPath $programTcl -TclArguments "{ $JtagServerPort $pdsPath }" `
        -WorkingDirectory $root -OutputPath $LogPath
    Assert-Pg2l100hScan -Text $programText -Source $LogPath

    $scanPosition = $programText.IndexOf('Executing : cfg_scan_chain')
    $assignPosition = $programText.IndexOf("Executing : cfg_assign_file -file $pdsPath -device_index 0")
    $programPosition = $programText.IndexOf('Executing : cfg_program -device_index 0')
    $disconnectPosition = $programText.IndexOf('Executing : cfg_disconnect')
    if ($scanPosition -lt 0 -or $assignPosition -le $scanPosition -or
        $programPosition -le $assignPosition -or $disconnectPosition -le $programPosition) {
        throw "PDS did not preserve the required scan/assign/program/disconnect order; inspect $LogPath"
    }
    if (!$programText.Contains('COMMAND[Program] execute successfully') -or
        !$programText.Contains('The done bit is 1')) {
        throw "PDS did not report successful volatile CRAM programming; inspect $LogPath"
    }
    $programEvidence.device = 'PG2L100H'
    $programEvidence.device_id = '0x00602899'
    $programEvidence.device_count = 1
    $programEvidence.device_index = 0
    $programEvidence.program_log_sha256 = (Get-FileHash -LiteralPath $LogPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $programEvidence.preflight_log_sha256 = (Get-FileHash -LiteralPath $preflightLog -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($requiresProjectEvidence) {
        # Re-check after configuration as well: a concurrent source/output edit
        # must never be attributed to the image just loaded.
        Assert-ProjectBitstreamEvidence -Root $root -Bitstream $resolvedSbit -ExpectedHash $sbitHash
        $identityAfterProgram = Get-ProgramProjectIdentity $root
        foreach ($name in $identityBeforeProgram.Keys) {
            if ($identityBeforeProgram[$name] -cne $identityAfterProgram[$name]) { throw "Build identity changed during CRAM programming: $name" }
            $programEvidence[$name] = $identityBeforeProgram[$name]
        }
    }
    $programEvidence.status = 'PASS'
    Write-Host "CRAM_PROGRAM_PASS: PG2L100H index 0; SHA-256 $sbitHash; log: $LogPath"
} finally {
    if ($startedServer -and $serverProcess -and !$serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id
    }
    if ($programEvidence) {
        $programEvidence.completed_utc = [DateTime]::UtcNow.ToString('o')
        [IO.File]::WriteAllText($EvidencePath, ($programEvidence | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
        Write-Host "CRAM_EVIDENCE: $EvidencePath ($($programEvidence.status))"
    }
}
