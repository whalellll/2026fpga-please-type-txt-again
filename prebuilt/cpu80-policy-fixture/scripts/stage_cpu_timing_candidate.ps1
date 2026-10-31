param(
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][ValidateSet(9,12,13,14,15,16,17,18)][int]$Divisor,
    [Parameter(Mandatory=$true)][string]$DtcPath,
    [string]$SourceRoot = '',
    [string]$CpuSourceRepo = '',
    [ValidateSet('video891','dedicated850p5','dedicated675')][string]$CpuClockSource = ''
)
# Freeze a separate source tree before the ordinary ADS / same-ADF PnR flow.
$ErrorActionPreference='Stop'
if(!$SourceRoot){$SourceRoot=Split-Path -Parent $PSScriptRoot}
$SourceRoot=[IO.Path]::GetFullPath($SourceRoot).TrimEnd('\','/')
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot).TrimEnd('\','/')
if(Test-Path -LiteralPath $OutputRoot){throw 'Candidate destination must be new'}
. (Join-Path $SourceRoot 'scripts/build_snapshot.ps1')
$names=@(Get-FpgaInputPaths $SourceRoot)
$names+=@('AGENTS.md','README.md','linux/soc.dts','linux/boot/soc.dtb')
foreach($directory in @('scripts','config','sim','skills')){
    $names+=@(Get-ChildItem -LiteralPath (Join-Path $SourceRoot $directory) -Recurse -File |
        Where-Object FullName -NotMatch '[\\/]__pycache__[\\/]' |
        ForEach-Object {$_.FullName.Substring($SourceRoot.Length+1).Replace('\','/')})
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$before=[ordered]@{}
foreach($name in @($names | Sort-Object -Unique)){
    $src=Get-FpgaSafePath $SourceRoot $name
    $dst=Get-FpgaSafePath $OutputRoot $name
    New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst
    $before[$name]=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
}
if($CpuSourceRepo){
    $profile=Get-Content -LiteralPath (Join-Path $CpuSourceRepo 'cpu/generated/core/emit-config.json') -Raw | ConvertFrom-Json
    & (Join-Path $OutputRoot 'scripts/sync_cpu.ps1') -SourceRepo $CpuSourceRepo -AllowSupervisorCandidate:($profile.supervisor -eq $true)
}
$clock=Get-Content -LiteralPath (Join-Path $OutputRoot 'config/clocks.json') -Raw | ConvertFrom-Json
. (Join-Path $OutputRoot 'scripts/clock_policy.ps1')
$targetMode=if($CpuClockSource -ceq 'dedicated675'){2}elseif($CpuClockSource -ceq 'dedicated850p5'){1}elseif($CpuClockSource -ceq 'video891'){0}else{Get-SocCpuClockMode $clock}
if($clock.cpu_divisor -ne $Divisor -or (Get-SocCpuClockMode $clock) -ne $targetMode){
    & (Join-Path $OutputRoot 'scripts/set_clock_candidate.ps1') -Root $OutputRoot -Divisor $Divisor -CpuClockSource $CpuClockSource -DtcPath $DtcPath -Apply
}else{
    & (Join-Path $OutputRoot 'scripts/check_clock_config.ps1') -Root $OutputRoot
}
$after=[ordered]@{}
foreach($name in $before.Keys){
    $after[$name]=(Get-FileHash -LiteralPath (Join-Path $OutputRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record=[ordered]@{schema=1;kind='isolated-cpu-timing-candidate';created_utc=[DateTime]::UtcNow.ToString('o');
    source_root=$SourceRoot;cpu_source_repository=$CpuSourceRepo;cpu_divisor=$Divisor;
    copied_inputs=$before;prepared_inputs=$after;changed=@($before.Keys | Where-Object {$before[$_] -cne $after[$_]});
    status='SOURCE_STAGED_ONLY';note='No synthesis, PnR, hardware programming, or board acceptance is performed by this helper.'}
[IO.File]::WriteAllText((Join-Path $OutputRoot 'candidate-stage.json'),($record | ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "CPU_TIMING_CANDIDATE_STAGED root=$OutputRoot changed=$($record.changed.Count)"
