param(
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][ValidateSet(9,10,12,13,14,15,16,17,18,27,36)][int]$Divisor,
    [Parameter(Mandatory=$true)][string]$DtcPath,
    [string]$SourceRoot = '',
    [string]$CpuSourceRepo = '',
    [ValidateSet('video891','dedicated850p5','dedicated675','dedicated800','dedicated1080frac','dedicated1147p5frac','dedicated945frac')][string]$CpuClockSource = '',
    [switch]$DisableLegacyH128
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
$targetMode=if($CpuClockSource -ceq 'dedicated945frac'){6}elseif($CpuClockSource -ceq 'dedicated1147p5frac'){5}elseif($CpuClockSource -ceq 'dedicated1080frac'){4}elseif($CpuClockSource -ceq 'dedicated800'){3}elseif($CpuClockSource -ceq 'dedicated675'){2}elseif($CpuClockSource -ceq 'dedicated850p5'){1}elseif($CpuClockSource -ceq 'video891'){0}else{Get-SocCpuClockMode $clock}
if($clock.cpu_divisor -ne $Divisor -or (Get-SocCpuClockMode $clock) -ne $targetMode){
    & (Join-Path $OutputRoot 'scripts/set_clock_candidate.ps1') -Root $OutputRoot -Divisor $Divisor -CpuClockSource $CpuClockSource -DtcPath $DtcPath -Apply
}else{
    & (Join-Path $OutputRoot 'scripts/check_clock_config.ps1') -Root $OutputRoot
}
if($DisableLegacyH128){
 $path=Join-Path $OutputRoot 'rtl/soc/soc_top.v';$top=[IO.File]::ReadAllText($path)
 if([regex]::Matches($top,'parameter integer ENABLE_H128_SPARSE = 1\b').Count -ne 1){throw 'Legacy H128 disable requires one explicit enabled anchor'}
 [IO.File]::WriteAllText($path,($top -replace 'parameter integer ENABLE_H128_SPARSE = 1\b','parameter integer ENABLE_H128_SPARSE = 0'),[Text.UTF8Encoding]::new($false))
}
$after=[ordered]@{}
foreach($name in $before.Keys){
    $after[$name]=(Get-FileHash -LiteralPath (Join-Path $OutputRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$rom=Join-Path $OutputRoot 'artifacts/bootrom.hex'
$romAlias=Join-Path $OutputRoot 'pds/bootrom.hex'
Copy-Item -LiteralPath $rom -Destination $romAlias
$romHash=(Get-FileHash -LiteralPath $rom -Algorithm SHA256).Hash.ToLowerInvariant()
if((Get-FileHash -LiteralPath $romAlias -Algorithm SHA256).Hash.ToLowerInvariant() -cne $romHash){throw 'Staged PDS ROM alias differs from frozen ROM'}
$cpuSourceHash=(Get-FileHash -LiteralPath (Join-Path $OutputRoot 'rtl/cpu/source.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$firmware=Get-Content -LiteralPath (Join-Path $OutputRoot 'artifacts/bootloader.build.json') -Raw | ConvertFrom-Json
$firmwareCpuSource=$firmware.build_inputs.'rtl/cpu/source.json'
$record=[ordered]@{schema=1;kind='isolated-cpu-timing-candidate';created_utc=[DateTime]::UtcNow.ToString('o');
    source_root=$SourceRoot;cpu_source_repository=$CpuSourceRepo;cpu_divisor=$Divisor;
    copied_inputs=$before;prepared_inputs=$after;generated_aliases=@{'pds/bootrom.hex'=$romHash};changed=@($before.Keys | Where-Object {$before[$_] -cne $after[$_]});
    firmware_cpu_binding=@{current_cpu_source_sha256=$cpuSourceHash;manifest_cpu_source_sha256=$firmwareCpuSource;matches=($cpuSourceHash -ceq $firmwareCpuSource);rebuild_required=($cpuSourceHash -cne $firmwareCpuSource)};
    status='SOURCE_STAGED_ONLY';note='No synthesis, PnR, hardware programming, or board acceptance is performed by this helper. Rebuild firmware before freezing if firmware_cpu_binding.rebuild_required is true, even when ELF/BIN/ROM remain byte-identical.'}
[IO.File]::WriteAllText((Join-Path $OutputRoot 'candidate-stage.json'),($record | ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "CPU_TIMING_CANDIDATE_STAGED root=$OutputRoot changed=$($record.changed.Count)"
