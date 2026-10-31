param([ValidateSet('r01','r02','r03','r04','r05','r06')][string]$Revision='r01')
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$target='D:/picture-p21-regression-20261020'
if($Revision -ne 'r01'){$target+='-'+$Revision}
$output=Join-Path $repo ('build/picture-p21-native/regression-'+$Revision)
$env:PATH='D:/LJL/WORK/msys64/ucrt64/bin;'+$env:PATH
Add-Type -Path (Join-Path $repo 'scripts/bounded_process.cs')
$arguments='-NoProfile -ExecutionPolicy Bypass -File '+$target+'/scripts/run_all_tests.ps1 -ToolchainBin D:/p17-gcc16-lto/native/bin -PythonPath '+$repo+'/build/picture-tools/python3144/python.exe -HostGccPath D:/LJL/WORK/msys64/ucrt64/bin/gcc.exe -PdsRoot D:/LJL/WORK/pango/PDS_2022.2-SP6.4'
$code=[CpuSimulation.BoundedProcess]::Run('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',$arguments,$target,
 (Join-Path $output 'stdout.log'),(Join-Path $output 'stderr.log'),1200)
Write-Output "P21_FULL_REGRESSION_EXIT=$code"
exit $code
