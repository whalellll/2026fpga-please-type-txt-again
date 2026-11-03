param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$count=0
function Reject([scriptblock]$Action) {
    $rejected=$false
    try { & $Action | Out-Null } catch { $rejected=$true }
    if (!$rejected) { throw 'Invalid compiler profile was accepted.' }
    $script:count++
}
$expected='-O2 -fno-if-conversion -fno-if-conversion2 -funroll-loops --param=max-unroll-times=2 -flto -mbranch-cost=1'
$selected=[pscustomobject]@{zbc_candidate=$true;coremark_compiler_profile='cm60-unroll2-lto-branch1'}
if (((Resolve-CpuCoremarkOptimization $selected) -join ' ') -cne $expected) { throw 'Wrong selected compiler recipe.' };$count++
if (((Resolve-CpuCoremarkOptimization $null) -join ' ') -cne '-O2') { throw 'Legacy default changed.' };$count++
if (((Resolve-CpuCoremarkOptimization ([pscustomobject]@{})) -join ' ') -cne '-O2') { throw 'Legacy empty profile changed.' };$count++
if (((Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate=$true})) -join ' ') -cne '-O2 -fno-if-conversion -fno-if-conversion2') { throw 'Legacy Zbc profile changed.' };$count++
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate=$false;coremark_compiler_profile='cm60-unroll2-lto-branch1'}) }
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{coremark_compiler_profile='cm60-unroll2-lto-branch1'}) }
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate='true'}) }
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate=$true;coremark_compiler_profile=1}) }
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate=$true;coremark_compiler_profile='CM60-unroll2-lto-branch1'}) }
Reject { Resolve-CpuCoremarkOptimization ([pscustomobject]@{zbc_candidate=$true;coremark_compiler_profile='unknown'}) }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'result.json'),(@{status='PASS';checks=$count;scope='Recipe selection and strict malformed/ISA-gating regressions'}|ConvertTo-Json)+"`n")
"COREMARK_CM60_PROFILE_PASS checks=$count"
