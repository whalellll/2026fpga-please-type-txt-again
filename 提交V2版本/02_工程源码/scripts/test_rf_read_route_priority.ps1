param([Parameter(Mandatory=$true)][string]$OutputDirectory,[switch]$BaseProbe)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(!$out.StartsWith('G:\fpga\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){throw 'New fixture output must be underG:/fpga'}
New-Item -ItemType Directory -Path (Join-Path $out 'fixture/config') -Force|Out-Null
New-Item -ItemType Directory -Path (Join-Path $out 'fixture/pds') -Force|Out-Null
$fixture=Join-Path $out 'fixture';$profilePath=Join-Path $fixture 'config/rf_read_route_priority.json'
foreach($directory in @('rtl','sw','ip','scripts')){New-Item -ItemType Directory -Path (Join-Path $fixture $directory) -Force|Out-Null}
$rcf=Join-Path $fixture 'pds/ddr3_test.rcf'
$targets=@(
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_dispatch_io_robRaddr_0 [3]'
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_dispatch_io_robRaddr_2 [3]'
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/registerFile/N3080 [1]'
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/registerFile/N3090 [0]'
 'u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/registerFile/N3089'
)
$profile=@{schema=1;profile='cpu80_rf_read_a10eb164_v1';source_native_run='a10eb164c38a485781ec4e2a431019c1';source_report_sha256='d38e2508e9bbdcef7deca5c0c366716cd1c0489a0359b49a035a8bc5c7ed95be';targets=$targets}
if($BaseProbe){
 $targets+=@('u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/N3697 [3]','u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/registerFile/N3100 [1]','u_cpu/u_cpu_wrapper/u_cpu/core/_N116458')
 $profile.profile='cpu80_rf_baseprobe_8772706c_v1';$profile.source_native_run='8772706c4ebe4e1fbf8363b23872f18e';$profile.source_report_sha256='f4fd686e28f0a69e54b9dfc0fd1e8174fbf5cd78583333b6048c4fc1c19a64a2';$profile.targets=$targets
}
$expectedTotal=20+$targets.Count
function Save-Profile($Value){[IO.File]::WriteAllText($profilePath,($Value|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))}
$checks=[Collections.Generic.List[string]]::new()
function Reject([string]$CaseLabel,[scriptblock]$Action){$rejected=$false;try{&$Action}catch{$rejected=$true};if(!$rejected){throw "Mutation accepted: $CaseLabel"};$checks.Add($CaseLabel)}
if(@(Get-FpgaDdrRouteLines).Count -ne 20 -or @(Get-FpgaDdrRouteLines $fixture).Count -ne 20){throw 'Legacy no-profile contract changed'}
$checks.Add('legacy20_without_profile')
Save-Profile $profile
$base=@(Get-FpgaDdrRouteLines);$extra=@($targets|ForEach-Object {'def_route -prior_net {'+$_+'}'});$all=@($base)+@($extra)
if(((Get-FpgaDdrRouteLines $fixture)-join "`n") -cne ($all-join "`n") -or $all.Count -ne $expectedTotal){throw 'Explicit profile differs from independent target list'}
[IO.File]::WriteAllLines($rcf,$all)
$project='(_widget wgt_edit_route_cons (_attribute _click_to_run (_switch ON)) (_input (_file "ddr3_test.rcf" (_format rcf) (_timespec "2026-10-29T00:00:00"))))'
$parse="Executing : add_constraint soc.fdc successfully.`nExecuting : add_constraint ddr3_test.rcf successfully."
$nativeLog=($all|ForEach-Object {'Executing : '+$_+' successfully.'})-join "`n"
$nets=($all|ForEach-Object {$_.Substring('def_route -prior_net {'.Length).TrimEnd('}')+';'})-join "`n"
Assert-FpgaDdrRouteRegistration $fixture $project $parse $nativeLog $nets
$checks.Add(('profile'+$expectedTotal+'_all_native_executions_and_actual_nets'))
$bare=$nativeLog.Replace('def_route -prior_net {'+$targets[4]+'}','def_route -prior_net '+$targets[4])
Assert-FpgaDdrRouteRegistration $fixture $project $parse $bare $nets
$checks.Add('real_native_scalar_unbraced_spelling')
foreach($name in $targets){
 $line='def_route -prior_net {'+$name+'}';$success='Executing : '+$line+' successfully.'
 Reject ('missing native '+$name) {Assert-FpgaDdrRouteRegistration $fixture $project $parse ($nativeLog.Replace($success,'')) $nets}
 Reject ('duplicate native '+$name) {Assert-FpgaDdrRouteRegistration $fixture $project $parse ($nativeLog+"`n"+$success) $nets}
 Reject ('failed native '+$name) {Assert-FpgaDdrRouteRegistration $fixture $project $parse ($nativeLog.Replace($success,$success.Replace('successfully','failed'))) $nets}
 Reject ('missing real mapped net '+$name) {Assert-FpgaDdrRouteRegistration $fixture $project $parse $nativeLog ($nets.Replace($name+';',''))}
 [IO.File]::WriteAllLines($rcf,@($all|Where-Object {$_ -cne $line}))
 Reject ('missing RCF target '+$name) {Assert-FpgaDdrRouteInput $fixture $project}
 [IO.File]::WriteAllLines($rcf,$all)
}
foreach($key in @('schema','profile','source_native_run','source_report_sha256')){
 $bad=$profile.Clone();$bad[$key]=if($key -eq 'schema'){2}else{'unreviewed'};Save-Profile $bad
 Reject ('wrong profile binding '+$key) {Get-FpgaDdrRouteLines $fixture|Out-Null}
}
$targetCases=@(
 [pscustomobject]@{label='missing';values=@($targets[0..($targets.Count-2)])}
 [pscustomobject]@{label='reordered';values=@($targets[1],$targets[0])+@($targets[2..($targets.Count-1)])}
 [pscustomobject]@{label='extra';values=(@($targets)+@('unknown'))}
)
foreach($mutation in $targetCases){
 $bad=$profile.Clone();$bad['targets']=$mutation.values;Save-Profile $bad
 Reject ('profile_target_'+$mutation.label) {Get-FpgaDdrRouteLines $fixture|Out-Null}
}
Save-Profile $profile
[IO.File]::Move($profilePath,($profilePath+'.saved'))
Reject ('twenty_default_rejects'+$expectedTotal+'_without_profile') {Assert-FpgaDdrRouteInput $fixture $project}
[IO.File]::Move(($profilePath+'.saved'),$profilePath)
[IO.File]::WriteAllLines($rcf,$all[1..($all.Count-1)])
Reject 'original_vendor_gate_remains_required' {Assert-FpgaDdrRouteInput $fixture $project}
[IO.File]::WriteAllLines($rcf,$all)
$inputs=@(Get-FpgaInputPaths $fixture)
if($inputs -cnotcontains 'config/rf_read_route_priority.json'){throw 'Explicit profile absent from native frozen input list'}
$checks.Add('profile_frozen_in_native_inputs')
$record=[ordered]@{status='RF_READ_PRIORITY_PROFILE_DEFAULT20_EXPLICIT_PROFILE_NATIVE_EXECUTION_AND_NET_NEGATIVES_PASS_NOT_NATIVE';profile=$profile.profile;expected_routes=$expectedTotal;checks=@($checks);count=$checks.Count;checker_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'build_snapshot.ps1')).Hash.ToLowerInvariant();test_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash.ToLowerInvariant();hardware_accessed=$false}
[IO.File]::WriteAllText((Join-Path $out 'result.json'),($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output ($record.status+' checks='+$checks.Count)
