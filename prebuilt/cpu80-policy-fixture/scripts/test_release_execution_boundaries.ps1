param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_pnr_budget.ps1')
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('release-boundary-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
if (!('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs') }
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'program_cram.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'program_cram parse failure' }
foreach ($name in @('Assert-NewConfigurationEvidencePaths','Get-ProgramProjectIdentity','Invoke-ConfigurationShell')) {
    $definition = @($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}, $true) | Where-Object { $_.Name -ceq $name })
    if ($definition.Count -ne 1) { throw "Missing production helper $name" }
    . ([scriptblock]::Create($definition[0].Extent.Text))
}
$checks = 0
function Expect-Failure([scriptblock]$Action, [string]$Pattern) {
    $message = ''
    try { & $Action | Out-Null } catch { $message = $_.Exception.ToString() }
    if ($message -notmatch $Pattern) { throw "Expected '$Pattern', got '$message'" }
    $script:checks++
}
try {
    $log = Join-Path $temporary 'operation.log'
    $errorLog = $log + '.stderr.txt'
    Assert-NewConfigurationEvidencePaths @($log, $errorLog)
    $checks++
    Expect-Failure { Assert-NewConfigurationEvidencePaths @($log, $log.ToUpperInvariant()) } 'collides'
    [IO.File]::WriteAllText($errorLog, 'existing raw evidence', $utf8)
    Expect-Failure { Assert-NewConfigurationEvidencePaths @($log, $errorLog) } 'exists'
    Remove-Item -LiteralPath $errorLog
    $standin = Join-Path $temporary 'safe-native-standin.ps1'
    [IO.File]::WriteAllText($standin, 'param([Alias("args")][string]$TclFixtureArgs,[string]$work_dir,[string]$report_dir) Write-Output ("ARGS=" + $TclFixtureArgs); Write-Output ("WORK=" + $work_dir)', $utf8)
    $OperationTimeoutSeconds = 20
    $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $output = Invoke-ConfigurationShell -ConfigShell $powershell -TclPath $standin -TclArguments '{ 65420 D:/SYNTHETIC/soc_top.sbit }' -WorkingDirectory $temporary -OutputPath $log
    if (!$output.Contains('ARGS={ 65420 D:/SYNTHETIC/soc_top.sbit }') -or !$output.Contains("WORK=$temporary")) { throw 'Bounded argv transport changed' }
    $checks++
    [IO.File]::WriteAllText($standin, 'exit 7', $utf8)
    Expect-Failure { Invoke-ConfigurationShell $powershell $standin '{ 65420 }' $temporary (Join-Path $temporary 'nonzero.log') } 'exited with code 7'
    [IO.File]::WriteAllText($standin, '[Console]::Error.WriteLine("E: synthetic vendor error"); exit 0', $utf8)
    Expect-Failure { Invoke-ConfigurationShell $powershell $standin '{ 65420 }' $temporary (Join-Path $temporary 'error-zero.log') } 'error despite exit 0'
    [IO.File]::WriteAllText($standin, 'Start-Sleep -Seconds 10', $utf8)
    $OperationTimeoutSeconds = 1
    $watch = [Diagnostics.Stopwatch]::StartNew()
    Expect-Failure { Invoke-ConfigurationShell $powershell $standin '{ 65420 }' $temporary (Join-Path $temporary 'timeout.log') } 'timed out|timeout'
    if ($watch.Elapsed.TotalSeconds -gt 6) { throw 'Bounded native standin outlived timeout margin' }
    $ledgerPath = Join-Path $temporary 'budget.json'
    $snapshot = Join-Path $temporary 'snapshot.json'
    [IO.File]::WriteAllText($snapshot, '{"synthetic_fixture":true}', $utf8)
    $now = [DateTimeOffset]::UtcNow
    $ledger = [ordered]@{schema=1; task_started=$now.AddSeconds(-1).ToString('o');deadline=$now.AddHours(23).ToString('o');maximum_full_pnr_starts=6;attempts=@()}
    [IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 8), $utf8)
    foreach ($i in 1..4) { Register-PnrAttempt $ledgerPath "search$i" 'search' $snapshot | Out-Null }
    Register-PnrAttempt $ledgerPath 'early-final' 'final' $snapshot | Out-Null
    Expect-Failure { Register-PnrAttempt $ledgerPath 'another-final' 'final' $snapshot } 'reserved'
    Register-PnrAttempt $ledgerPath 'control-six' 'same_frequency' $snapshot | Out-Null
    $counted = [IO.File]::ReadAllText($ledgerPath) | ConvertFrom-Json
    foreach ($attempt in $counted.attempts) { $attempt.status = 'CANCELLED_OR_FAILED_FIXTURE' }
    [IO.File]::WriteAllText($ledgerPath, ($counted | ConvertTo-Json -Depth 8), $utf8)
    Expect-Failure { Register-PnrAttempt $ledgerPath 'new-seed-retry' 'search' $snapshot } 'limit'
    $checks++
    $ledger.task_started = $now.AddHours(1).ToString('o'); $ledger.deadline = $now.AddHours(24).ToString('o')
    [IO.File]::WriteAllText($ledgerPath, ($ledger | ConvertTo-Json -Depth 8), $utf8)
    Expect-Failure { Get-PnrCampaignSeconds $ledgerPath 'search' } 'policy'
    [IO.File]::WriteAllText((Join-Path $temporary 'VERSION'), '6.5', $utf8)
    Expect-Failure { Resolve-PnrCampaignBudget $temporary '' } 'Missing campaign budget ledger'
    Write-Output "RELEASE_EXECUTION_BOUNDARIES_PASS checks=$checks NO_PDS_NO_JTAG safe_powershell_standins_only=true"
} finally {
    $prefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\release-boundary-'
    if (!$temporary.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
        @(Get-ChildItem -LiteralPath $temporary -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Unsafe fixture cleanup' }
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
