param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$ToolchainBin = '',
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
    [string]$PdsRoot = '',
    [string]$VendorModels = '',
    [string]$PllWslDistro = '',
    [string]$MacPeWslDistro = '',
    [ValidateRange(10,3600)][int]$MacPeTimeoutSeconds = 600,
    [string]$PolicyFixtureRoot = '',
    [ValidateRange(10,900)][int]$PllTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$cpuOriginalPath = $env:PATH
try {
if(Test-Path -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'pds/cpu75_csr_reference.pcf')) {
    & $PythonPath -B (Join-Path $PSScriptRoot 'test_cpu_csr_placement.py')
    if($LASTEXITCODE -ne 0){throw 'CPU75 strict CSR placement contract regression failed'}
}
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
$metadataEvidence = Join-Path ([IO.Path]::GetTempPath()) ('weight-metadata-' + [guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_weight_metadata_equivalence.py') --output $metadataEvidence `
    --iverilog (Join-Path $IcarusBin 'iverilog.exe') --vvp (Join-Path $IcarusBin 'vvp.exe')
if ($LASTEXITCODE -ne 0) { throw "Weight metadata cycle-equivalence failed; inspect $metadataEvidence" }
Write-Output "WEIGHT_METADATA_EVIDENCE=$metadataEvidence"
& (Join-Path $PSScriptRoot 'test_riscv_toolchain.ps1') -ToolchainBin $ToolchainBin
& (Join-Path $PSScriptRoot 'test_coremark_measurement.ps1')
& $PythonPath -B (Join-Path $PSScriptRoot 'test_conv_resource_contract.py')
if ($LASTEXITCODE -ne 0) { throw 'Convolution native resource gate fixtures failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_dense_pe_resource_contract.py')
if ($LASTEXITCODE -ne 0) { throw 'Dense native full/half/quarter resource profiles failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_nnue_voice_resource_contract.py')
if ($LASTEXITCODE -ne 0) { throw 'NNUE/voice native resource profiles failed' }
& (Join-Path $PSScriptRoot 'test_cpu_dedicated_clock.ps1')
& (Join-Path $PSScriptRoot 'test_cpu75_clock.ps1')
& (Join-Path $PSScriptRoot 'test_cpu80_clock.ps1')
& (Join-Path $PSScriptRoot 'test_cpu80_frac_clock.ps1')
$pll80Evidence=Join-Path ([IO.Path]::GetTempPath()) ('cpu80-pll-'+[guid]::NewGuid().ToString('N'))
$pllPlatformArgs=@('--timeout-seconds',"$PllTimeoutSeconds")
if($PllWslDistro){$pllPlatformArgs+=@('--wsl-distro',$PllWslDistro)}
& $PythonPath -B (Join-Path $PSScriptRoot 'test_cpu80_pll.py') --icarus-bin $IcarusBin --vendor-models $VendorModels --output $pll80Evidence @pllPlatformArgs
if ($LASTEXITCODE -ne 0) { throw "CPU80 PLL waveform regression failed; inspect $pll80Evidence" }
$frac80Evidence=Join-Path ([IO.Path]::GetTempPath()) ('cpu80-frac-pll-'+[guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_cpu80_pll.py') --fractional --icarus-bin $IcarusBin --vendor-models $VendorModels --output $frac80Evidence @pllPlatformArgs
if ($LASTEXITCODE -ne 0) { throw "CPU80 fractional PLL waveform regression failed; inspect $frac80Evidence" }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_synthesis_only.py')
if ($LASTEXITCODE -ne 0) { throw 'Synthesis-only control-flow regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_frontend_folded_controls.py')
if ($LASTEXITCODE -ne 0) { throw 'Folded frontend consumer audit regression failed' }
foreach ($clockBootTest in @('test_clock_boot_word_crc.py', 'test_clock_boot_gather_dts.py', 'test_clock_boot_reserved_mmio.py', 'test_clock_boot_cpu80.py')) {
    & $PythonPath -B (Join-Path $PSScriptRoot $clockBootTest)
    if ($LASTEXITCODE -ne 0) { throw "Clock boot contract regression failed: $clockBootTest" }
}
$policyFixtureArgs=@()
if($PolicyFixtureRoot){$policyFixtureArgs=@('--fixture-root',$PolicyFixtureRoot)}
& $PythonPath -B (Join-Path $PSScriptRoot 'test_board_release.py') --host-gcc $HostGccPath @policyFixtureArgs
if ($LASTEXITCODE -ne 0) { throw 'BoardRelease acceptance policy regression failed' }
& (Join-Path $PSScriptRoot 'test_delivery_mode_policy.ps1') -PythonPath $PythonPath
& (Join-Path $PSScriptRoot 'test_program_cram_evidence.ps1')
& $PythonPath -B (Join-Path $PSScriptRoot 'test_uart_tx_pad_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'UART ADS mapping policy regression failed' }
& (Join-Path $PSScriptRoot 'test_uart_tx_pad_contract.ps1')
$uartEvidence = Join-Path ([IO.Path]::GetTempPath()) ('uart-pad-regression-' + [guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_uart_tx_fifo_hold_pad.py') `
    --icarus-bin $IcarusBin --vendor-models $VendorModels --output-directory $uartEvidence
if ($LASTEXITCODE -ne 0) { throw "UART RTL/vendor primitive regression failed; inspect $uartEvidence" }
Write-Output "UART_PAD_REGRESSION_EVIDENCE=$uartEvidence"
& $PythonPath -B (Join-Path $PSScriptRoot 'test_mac_weight_pad_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'Weight pad ADS mutation regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_rob_vaddr_pad_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'ROB vaddr pad/head ADS mutation regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_fallback_target_pad_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'Fallback target pad ADS mutation regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_ib_rf_metadata_binding.py')
if ($LASTEXITCODE -ne 0) { throw 'IB RF source-capability binding regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_sd_write_ownership_ads.py')
if ($LASTEXITCODE -ne 0) { throw 'SD write ownership SAT/mutation regression failed' }
$carryEvidence=Join-Path ([IO.Path]::GetTempPath()) ('ads-carry-'+[guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_ads_carry_vendor.py') --icarus-bin $IcarusBin --vendor-models $VendorModels --output $carryEvidence
if ($LASTEXITCODE -ne 0) { throw "Carry ADS/vendor equivalence failed; inspect $carryEvidence" }
$weightEvidence=Join-Path ([IO.Path]::GetTempPath()) ('weight-pad-'+[guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_mac_weight_hold_pad.py') --icarus-bin $IcarusBin --vendor-models $VendorModels --output $weightEvidence
if ($LASTEXITCODE -ne 0) { throw "Weight pad behavior/vendor regression failed; inspect $weightEvidence" }

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
& $PythonPath -B (Join-Path $PSScriptRoot 'test_sd_zero_stage.py') `
    --gcc $HostGccPath --output (Join-Path ([IO.Path]::GetTempPath()) ('sd-zero-stage-'+[guid]::NewGuid().ToString('N')))
if ($LASTEXITCODE -ne 0) { throw 'SD bootstrap zero-address staging regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_mac_open_service.py') `
    --gcc $HostGccPath --output (Join-Path ([IO.Path]::GetTempPath()) ('mac-open-service-'+[guid]::NewGuid().ToString('N')))
if ($LASTEXITCODE -ne 0) { throw 'MAC private-context clear/service regression failed' }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_cpu80_approved_contract.py')
if ($LASTEXITCODE -ne 0) { throw 'Approved CPU80 release contract regression failed' }

& (Join-Path $PSScriptRoot 'build_sd_native_driver_test.ps1') `
    -IcarusBin $IcarusBin -ToolchainBin $ToolchainBin -MsysRoot $MsysRoot
if ($LASTEXITCODE -ne 0) { throw 'MicroSD native 4-bit driver test failed' }

& (Join-Path $PSScriptRoot 'run_soc_tests.ps1') -IcarusBin $IcarusBin
if ($LASTEXITCODE -ne 0) { throw 'SoC peripheral regression failed' }
$retiredEvidence=Join-Path ([IO.Path]::GetTempPath()) ('h128-retirement-'+[guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_h128_disabled.py') --icarus-bin $IcarusBin --output $retiredEvidence
if ($LASTEXITCODE -ne 0) { throw "H128 retirement regression failed; inspect $retiredEvidence" }
$peHoldEvidence=Join-Path ([IO.Path]::GetTempPath()) ('mac-pe-hold-'+[guid]::NewGuid().ToString('N'))
if ($MacPeWslDistro) {
    function Convert-PeTestWslPath([string]$Path) {
        $full=[IO.Path]::GetFullPath($Path)
        if($full -notmatch '^([A-Za-z]):\\(.*)$'){throw "Cannot convert PE test path: $full"}
        return '/mnt/'+$Matches[1].ToLowerInvariant()+'/'+$Matches[2].Replace('\','/')
    }
    & wsl.exe -d $MacPeWslDistro -u root -- python3 -B `
        (Convert-PeTestWslPath (Join-Path $PSScriptRoot 'test_mac_pe_hold.py')) `
        --root (Convert-PeTestWslPath (Split-Path -Parent $PSScriptRoot)) `
        --icarus-bin /usr/bin --output (Convert-PeTestWslPath $peHoldEvidence) --timeout-seconds $MacPeTimeoutSeconds
} else {
    & $PythonPath -B (Join-Path $PSScriptRoot 'test_mac_pe_hold.py') --icarus-bin $IcarusBin --output $peHoldEvidence --timeout-seconds $MacPeTimeoutSeconds
}
if ($LASTEXITCODE -ne 0) { throw "MAC PE result lifetime/equivalence regression failed; inspect $peHoldEvidence" }

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
$convEvidence=Join-Path ([IO.Path]::GetTempPath()) ('cpu80-conv-'+[guid]::NewGuid().ToString('N'))
& $PythonPath -B (Join-Path $PSScriptRoot 'test_cpu80_conv_integration.py') --icarus-bin $IcarusBin --output $convEvidence
if ($LASTEXITCODE -ne 0) { throw "Enabled-conv dense/gather isolation failed; inspect $convEvidence" }
& $PythonPath -B (Join-Path $PSScriptRoot 'test_conv_weight_fold.py') --icarus-bin $IcarusBin
if ($LASTEXITCODE -ne 0) { throw 'Convolution folded-weight equivalence failed' }
& (Join-Path $PSScriptRoot 'test_picture_host.ps1') -HostCompiler $HostGccPath -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) { throw 'Picture host regression failed' }
Write-Output 'SOC_ALL_TESTS_PASS'
} finally {
    $env:PATH = $cpuOriginalPath
}
