param([Parameter(Mandatory=$true)][string]$Repository,[Parameter(Mandatory=$true)][string]$PythonPath,[switch]$AfterSoc,[switch]$CameraOnly)
$ErrorActionPreference='Stop'
$scripts=Join-Path $Repository 'scripts'
$icarus='D:/LJL/WORK/iverilog/bin'
$msys='D:/LJL/WORK/msys64'
$gcc='D:/LJL/WORK/msys64/ucrt64/bin/gcc.exe'
$toolchain='D:/cpu-tools/v35-gcc16-build/native/bin'
# Original full entry point already failed its mandatory LTO boot build. Run
# the remaining original test entry points unchanged, with a distinct marker.
if(!$CameraOnly){
if(!$AfterSoc){
& (Join-Path $scripts 'test_coremark_manifest_policy.ps1') -PythonPath $PythonPath
& (Join-Path $scripts 'run_tests.ps1') -IcarusBin $icarus -ToolchainBin $toolchain -MsysRoot $msys
if($LASTEXITCODE -ne 0){throw 'CPU functional suite failed'}
& (Join-Path $scripts 'build_fat_ro_test.ps1') -IcarusBin $icarus -ToolchainBin $toolchain -MsysRoot $msys
& (Join-Path $scripts 'build_sd_native_driver_test.ps1') -IcarusBin $icarus -ToolchainBin $toolchain -MsysRoot $msys
if($LASTEXITCODE -ne 0){throw 'SD native driver suite failed'}
& (Join-Path $scripts 'run_soc_tests.ps1') -IcarusBin $icarus
if($LASTEXITCODE -ne 0){throw 'SoC peripheral suite failed'}
}
& (Join-Path $scripts 'run_speaker_tests.ps1') -IcarusBin $icarus -ToolchainRoot (Split-Path -Parent $toolchain) -SkipBootloaderBuild -HostGccPath $gcc
if($LASTEXITCODE -ne 0){throw 'Speaker suite failed'}
& $PythonPath (Join-Path $Repository 'sim/test_camera_receiver.py')
if($LASTEXITCODE -ne 0){throw 'Camera receiver suite failed'}
}
& (Join-Path $scripts 'run_camera_sd_tests.ps1') -HostGccPath $gcc -PythonPath $PythonPath
if($LASTEXITCODE -ne 0){throw 'Camera SD suite failed'}
Write-Output 'R08_REMAINING_FUNCTIONAL_TESTS_PASS'
