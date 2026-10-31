param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$ToolchainBin = '',
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
    [string]$PdsRoot = '',
    [string]$VendorModels = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$cpuOriginalPath = $env:PATH
try {
# Only read vendor simulation models; this regression never launches PDS.
if (!$VendorModels) {
    if ($PdsRoot) {
        $VendorModels = Join-Path $PdsRoot 'arch/vendor/pango/verilog/simulation'
    } else {
        $roots = @($env:PDS_ROOT, 'G:\fpga\PDS_2022.2-SP6.4', 'D:\LJL\WORK\pango\PDS_2022.2-SP6.4')
        foreach ($candidate in $roots) {
            if (!$candidate) { continue }
            $models = Join-Path $candidate 'arch/vendor/pango/verilog/simulation'
            if (Test-Path -LiteralPath (Join-Path $models 'GTP_LUT6D.v') -PathType Leaf) {
                $VendorModels = $models; break
            }
        }
    }
}
if (!$VendorModels) { throw 'UART primitive regression requires -VendorModels, -PdsRoot, or PDS_ROOT for PDS 2022.2-SP6.4.' }
$VendorModels = [IO.Path]::GetFullPath($VendorModels)
foreach ($model in @('GTP_LUT6D.v','GTP_LUT5.v','GTP_MUX2LUT6.v','INT_LUTMUX4_UDP.v','INT_LUTMUX2_UDP.v')) {
    if (!(Test-Path -LiteralPath (Join-Path $VendorModels $model) -PathType Leaf)) { throw "Missing UART vendor model: $model" }
}
$ToolchainBin = (Get-CpuToolchain -ToolchainBin $ToolchainBin).Bin
& (Join-Path $PSScriptRoot 'test_riscv_toolchain.ps1') -ToolchainBin $ToolchainBin
& (Join-Path $PSScriptRoot 'test_coremark_measurement.ps1')
& (Join-Path $PSScriptRoot 'test_cpu_dedicated_clock.ps1')
& (Join-Path $PSScriptRoot 'test_cpu75_clock.ps1')
& $PythonPath -B (Join-Path $PSScriptRoot 'test_synthesis_only.py')
if ($LASTEXITCODE -ne 0) { throw 'Synthesis-only control-flow regression failed' }
foreach ($clockBootTest in @('test_clock_boot_word_crc.py', 'test_clock_boot_gather_dts.py', 'test_clock_boot_reserved_mmio.py')) {
    & $PythonPath -B (Join-Path $PSScriptRoot $clockBootTest)
    if ($LASTEXITCODE -ne 0) { throw "Clock boot contract regression failed: $clockBootTest" }
}
& $PythonPath -B (Join-Path $PSScriptRoot 'test_board_release.py') --host-gcc $HostGccPath
if ($LASTEXITCODE -ne 0) { throw 'BoardRelease acceptance policy regression failed' }
& (Join-Path $PSScriptRoot 'test_delivery_mode_policy.ps1')
& (Join-Path $PSScriptRoot 'test_program_cram_evidence.ps1')
& $PythonPath -B (Join-Path $PSScriptRoot 'test_uart_tx_pad_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'UART ADS mapping policy regression failed' }
& (Join-Path $PSScriptRoot 'test_uart_tx_pad_contract.ps1')
$uartEvidence = Join-Path ([IO.Path]::GetTempPath()) ('uart-pad-regression-' + [guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_uart_tx_fifo_hold_pad.py') `
    --icarus-bin $IcarusBin --vendor-models $VendorModels --output-directory $uartEvidence
if ($LASTEXITCODE -ne 0) { throw "UART RTL/vendor primitive regression failed; inspect $uartEvidence" }
Write-Output "UART_PAD_REGRESSION_EVIDENCE=$uartEvidence"
& (Join-Path $PSScriptRoot 'run_cdc_tests.ps1') -IcarusBin $IcarusBin
& (Join-Path $PSScriptRoot 'build_bootloader.ps1') `
    -ToolchainRoot (Split-Path -Parent $ToolchainBin)
if ($LASTEXITCODE -ne 0) { throw 'Bootloader build failed' }
& (Join-Path $PSScriptRoot 'test_coremark_manifest_policy.ps1') -PythonPath $PythonPath

& (Join-Path $PSScriptRoot 'run_tests.ps1') `
    -IcarusBin $IcarusBin -ToolchainBin $ToolchainBin -MsysRoot $MsysRoot
if ($LASTEXITCODE -ne 0) { throw 'SoC CPU acceptance test failed' }

& (Join-Path $PSScriptRoot 'build_fat_ro_test.ps1') `
    -IcarusBin $IcarusBin -ToolchainBin $ToolchainBin -MsysRoot $MsysRoot
if ($LASTEXITCODE -ne 0) { throw 'MicroSD FAT reader test failed' }

& (Join-Path $PSScriptRoot 'build_sd_native_driver_test.ps1') `
    -IcarusBin $IcarusBin -ToolchainBin $ToolchainBin -MsysRoot $MsysRoot
if ($LASTEXITCODE -ne 0) { throw 'MicroSD native 4-bit driver test failed' }

& (Join-Path $PSScriptRoot 'run_soc_tests.ps1') -IcarusBin $IcarusBin
if ($LASTEXITCODE -ne 0) { throw 'SoC peripheral regression failed' }

& (Join-Path $PSScriptRoot 'run_speaker_tests.ps1') `
    -IcarusBin $IcarusBin `
    -ToolchainRoot (Split-Path -Parent $ToolchainBin) `
    -SkipBootloaderBuild -HostGccPath $HostGccPath
if ($LASTEXITCODE -ne 0) { throw 'Speaker playback regression failed' }

& (Join-Path $PSScriptRoot 'run_audio_capture_tests.ps1') -IcarusBin $IcarusBin
if ($LASTEXITCODE -ne 0) { throw 'Audio capture regression failed' }
& $PythonPath -B (Join-Path (Split-Path -Parent $PSScriptRoot) 'sim/test_voice_hw_contract.py')
if ($LASTEXITCODE -ne 0) { throw 'Voice hardware integration contract failed' }

& $PythonPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'sim/test_camera_receiver.py')
if ($LASTEXITCODE -ne 0) { throw 'Camera receiver integration regression failed' }
& (Join-Path $PSScriptRoot 'run_camera_sd_tests.ps1') -HostGccPath $HostGccPath -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) { throw 'Camera SD file regression failed' }
Write-Output 'SOC_ALL_TESTS_PASS'
} finally {
    $env:PATH = $cpuOriginalPath
}
