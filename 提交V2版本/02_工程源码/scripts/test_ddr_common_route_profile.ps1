param([Parameter(Mandatory=$true)][string]$WorkRoot)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$fixture=Join-Path $WorkRoot 'route-profile-tests-01/root'
New-Item -ItemType Directory -Path (Join-Path $fixture 'config'),(Join-Path $fixture 'pds') -Force | Out-Null
foreach($name in @('config/clocks.json','config/rf_read_route_priority.json','config/ddr_common_route_priority.json','pds/ddr3_test.rcf')) {
 Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $fixture $name)
}
$project=[IO.File]::ReadAllText((Join-Path $root 'pds/soc_gui.pds'))
Assert-FpgaDdrRouteInput $root $project
Assert-FpgaDdrRouteInput $fixture $project
if(@(Get-FpgaDdrRouteLines $root).Count -ne 31) {throw 'Expected20base+8RF+3common priorities'}
$path=Join-Path $fixture 'config/ddr_common_route_priority.json'
$original=[IO.File]::ReadAllText($path)
function Assert-Rejected([scriptblock]$Action) {
 $rejected=$false
 try { & $Action | Out-Null } catch { $rejected=$true }
 if(!$rejected){throw 'Corrupt route profile unexpectedly accepted'}
}
$cases=@('schema','profile','run','hash','ancestor','target','duplicate','missing','clock','extra-net')
foreach($case in $cases) {
 [IO.File]::WriteAllText($path,$original)
 $p=$original|ConvertFrom-Json
 switch($case) {
  schema {$p.schema=2}
  profile {$p.profile='unknown'}
  run {$p.source_native_run='wrong'}
  hash {$p.source_report_sha256=('0'*64)}
  ancestor {$p.base_source_report_sha256=('0'*64)}
  target {$p.targets=@('I_ips_ddr_top/wrong')}
  duplicate {$p.targets=@($p.targets[0],$p.targets[0])}
  missing {Remove-Item -LiteralPath $path}
  clock {
    $c=Get-Content -LiteralPath (Join-Path $fixture 'config/clocks.json') -Raw|ConvertFrom-Json
    $c.cpu_hz=100000000
    [IO.File]::WriteAllText((Join-Path $fixture 'config/clocks.json'),($c|ConvertTo-Json -Depth 10))
  }
  extra-net {Add-Content -LiteralPath (Join-Path $fixture 'pds/ddr3_test.rcf') -Value 'def_route -prior_net {unreviewed/net}'}
 }
 if($case -notin @('missing','clock','extra-net')){[IO.File]::WriteAllText($path,($p|ConvertTo-Json -Depth 8))}
 Assert-Rejected { Assert-FpgaDdrRouteInput $fixture $project }
 Copy-Item -LiteralPath (Join-Path $root 'config/clocks.json') -Destination (Join-Path $fixture 'config/clocks.json')
 Copy-Item -LiteralPath (Join-Path $root 'pds/ddr3_test.rcf') -Destination (Join-Path $fixture 'pds/ddr3_test.rcf')
}
[IO.File]::WriteAllText($path,$original)
Assert-FpgaDdrRouteInput $fixture $project
Write-Output 'DDR_COMMON_ROUTE_PROFILE_POSITIVE_AND_TEN_NEGATIVE_BINDINGS_PASS'
