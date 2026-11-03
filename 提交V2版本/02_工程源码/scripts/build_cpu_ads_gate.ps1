param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$ProjectRoot = '',
    [string]$EvidenceDirectory = ''
)
$ErrorActionPreference = 'Stop'
$root = if ($ProjectRoot) { [IO.Path]::GetFullPath($ProjectRoot) } else { Split-Path $PSScriptRoot -Parent }
. (Join-Path $root 'scripts/build_snapshot.ps1')
$snapshotPath = Join-Path $root 'pds/build_snapshot.json'
$declared = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json
$snapshot = Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
$folder = if ($EvidenceDirectory) { [IO.Path]::GetFullPath($EvidenceDirectory) } else {
    Join-Path $root ('pds/input-snapshots/' + $snapshot.run_id)
}
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$resultPath = Join-Path $folder 'cpu-pre-pnr.json'
if (Test-Path -LiteralPath $resultPath) { throw 'Pre-PnR CPU result already exists for this run; refuse to reuse it' }
$netlist = Join-Path $root 'pds/synthesize/soc_top_syn.vm'
$pikafishOnly=([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))) -match '\.PIKAFISH_ONLY\s*\(\s*1\s*\)'
if (!(Test-Path -LiteralPath $netlist -PathType Leaf)) { throw 'Pre-PnR ADS netlist is missing' }
if (-not ('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $root 'scripts/bounded_process.cs') }
$auditEntry = Join-Path $root 'scripts/audit_cpu_ads.py'
$halfOutputPmaAdapter = ([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))).Contains('.HALF_OUTPUT(1)') -and
    ((Get-Content -Raw -LiteralPath (Join-Path $root 'config/clocks.json') | ConvertFrom-Json).cpu_clock_source -ceq 'dedicated1147p5frac')
$voiceNnueAdapter = ([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))).Contains('.ENABLE_NNUE_PIPELINE(1)')
$integratedCpuAdapter = $voiceNnueAdapter -and ([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))).Contains('.CNN_ENABLE(1)') -and ([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))).Contains('.PIKAFISH_ONLY(1)') -and ([IO.File]::ReadAllText((Join-Path $root 'rtl/soc/soc_top.v'))) -match 'parameter integer ENABLE_VISION32_CANDIDATE = 1\b'
$halfOutputPmaAdapter = $halfOutputPmaAdapter -and !$voiceNnueAdapter
if ($halfOutputPmaAdapter) {
    $auditEntry = Join-Path $root 'scripts/audit_cpu85_half_ads.py'
    if (!(Test-Path -LiteralPath $auditEntry -PathType Leaf)) { throw 'Half-output PMA boundary adapter missing' }
}
if ($voiceNnueAdapter) { $auditEntry = Join-Path $root 'scripts/audit_voice_nnue75_ads.py' }
if ($integratedCpuAdapter) { $auditEntry = Join-Path $root 'scripts/audit_integrated60_ads.py' }
$arguments = '"' + $auditEntry + '" "' + $netlist +
    '" --input-snapshot "' + $snapshotPath + '" --output "' + $resultPath + '"'
$exitCode = [CpuSimulation.BoundedProcess]::Run($PythonPath, $arguments, $root,
    (Join-Path $folder 'cpu-pre-pnr.stdout.log'), (Join-Path $folder 'cpu-pre-pnr.stderr.log'), 300)
if ($exitCode -ne 0) { throw "Pre-PnR CPU ADS audit failed exit=$exitCode; inspect $folder/cpu-pre-pnr.*" }
$result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
Assert-FpgaRobOwnerContract $result $snapshot
if ($voiceNnueAdapter -and ($result.voice_nnue_ras_adapter.status -cne 'ACTUAL_RAS_PRODUCER_CORRELATION_AND_UNCHANGED_CPU_ORACLE_PASS' -or
    $result.voice_nnue_ras_adapter.adapter_sha256 -cne $snapshot.inputs.'scripts/audit_voice_nnue75_ads.py')) {
    throw 'Voice/NNUE RAS proof does not bind the actual producer and frozen adapter'
}
if ($halfOutputPmaAdapter -and (
    $result.pma_page_export_contract.status -cne 'NATIVE_PMA_PAGE_EXPORT_1024_CASES_PASS_NOT_STA' -or
    $result.pma_page_export_contract.cases -ne 1024 -or
    $result.pma_page_adapter_sha256 -cne $snapshot.inputs.'scripts/audit_cpu85_half_ads.py')) {
    throw 'Half-output PMA proof does not bind all1024 cases and the frozen adapter'
}
if ($integratedCpuAdapter -and (
    $result.integrated60_adapter.status -cne 'ACTUAL_PMA_AND_RAS_BOUNDARIES_WITH_UNCHANGED_CPU_ORACLE_PASS' -or
    $result.integrated60_adapter.adapter_sha256 -cne $snapshot.inputs.'scripts/audit_integrated60_ads.py' -or
    $result.pma_page_export_contract.status -cne 'NATIVE_PMA_PAGE_EXPORT_1024_CASES_PASS_NOT_STA' -or
    $result.pma_page_export_contract.cases -ne 1024 -or
    $result.pma_page_adapter_sha256 -cne $snapshot.inputs.'scripts/audit_cpu85_half_ads.py')) {
    throw 'Combined pre-PnR audit lacks exact frozen PMA producer/consumer and RAS proofs'
}
if ($result.schema_version -ne 1 -or $result.status -cne 'PASS' -or
    $result.frontend_cases -ne 85760 -or $result.return_cases -ne 10240 -or
    $result.pma_address_cases -ne 2144 -or $result.rsmem_hint_cases -ne 17152 -or
    $result.input_snapshot_run_id -cne $snapshot.run_id -or
    $result.input_snapshot_sha256 -cne (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $result.audit_script_sha256 -cne $snapshot.inputs.'scripts/audit_cpu_ads.py' -or
    $result.netlist_sha256 -cne (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Pre-PnR CPU ADS result is incomplete or does not bind the actual inputs'
}
Assert-FpgaCpuPmaContract $result
Assert-FpgaRobOwnerContract $result $snapshot
Assert-FpgaUartTxPadContract $result $snapshot
$null = Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
Write-Output "CPU_PRE_PNR_ADS_PASS run=$($snapshot.run_id) frontend=85760 returns=10240 pma=2144 hints=17152"

$clock=Get-Content -LiteralPath (Join-Path $root 'config/clocks.json') -Raw|ConvertFrom-Json
if((Get-SocCpuClockMode $clock) -ne 0){
    $clockOutput=Join-Path $folder 'cpu-clock-pre-pnr.json'
    if(Test-Path -LiteralPath $clockOutput){throw 'CPU clock ADS evidence already exists for this run'}
    $clockScript=Join-Path $root 'scripts/audit_cpu_dedicated_pll_ads.py'
    $clockArgs='"'+$clockScript+'" --netlist "'+$netlist+'" --clocks "'+(Join-Path $root 'config/clocks.json')+
        '" --resources "'+(Join-Path $root 'pds/synthesize/soc_top.snr')+'" --fdc "'+(Join-Path $root 'pds/soc.fdc')+'" --soc-top "'+(Join-Path $root 'rtl/soc/soc_top.v')+'" --output "'+$clockOutput+'"'
    $clockExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$clockArgs,$root,
        (Join-Path $folder 'cpu-clock-pre-pnr.stdout.log'),(Join-Path $folder 'cpu-clock-pre-pnr.stderr.log'),60)
    if($clockExit -ne 0){throw 'Native ADS CPU clock binding audit failed before PnR'}
    $clockAudit=Get-Content -LiteralPath $clockOutput -Raw|ConvertFrom-Json
    if($clockAudit.status -cne 'DEDICATED_CPU_PLL_ADS_PASS_NOT_STA_OR_BOARD' -or
        $clockAudit.native_cpu_clock_name -cne 'cpu_clk' -or
        $clockAudit.cpu_hz -ne $clock.cpu_hz -or $clockAudit.sys_hz -ne $clock.sys_hz -or
        $clockAudit.pll_vco_hz -ne $clock.cpu_pll_vco_hz -or
        $clockAudit.audit_script_sha256 -cne $snapshot.inputs.'scripts/audit_cpu_dedicated_pll_ads.py'){
        throw 'Native CPU clock ADS evidence does not bind the frozen checker'
    }
    Write-Output "CPU_CLOCK_PRE_PNR_ADS_PASS declared=cpu_clk actual_pll=$($clock.cpu_clock_source)"
}

# Prepared shifter operands must survive native synthesis at the existing FU edge.
# Legacy CPU profiles have no prepared-shift interface and retain their old gate.
$cpuRtlPath = Join-Path $root 'rtl/cpu/CoreTop.sv'
if ((Get-Content -LiteralPath $cpuRtlPath -Raw).Contains('io_shiftSrcPrepared')) {
    $shiftPath = Join-Path $folder 'prepared-shift-pre-pnr.json'
    if (Test-Path -LiteralPath $shiftPath) { throw 'Prepared-shift evidence already exists for this run' }
    $shiftArgs = '"' + (Join-Path $root 'scripts/audit_cpu_prepared_shift_ads.py') +
        '" --netlist "' + $netlist + '" --rtl "' + $cpuRtlPath +
        '" --input-snapshot "' + $snapshotPath + '" --output "' + $shiftPath + '"'
    $shiftExit = [CpuSimulation.BoundedProcess]::Run($PythonPath, $shiftArgs, $root,
        (Join-Path $folder 'prepared-shift-pre-pnr.stdout.log'), (Join-Path $folder 'prepared-shift-pre-pnr.stderr.log'), 60)
    if ($shiftExit -ne 0) { throw 'Prepared-shift native ADS retention failed before PnR' }
    $shift = Get-Content -LiteralPath $shiftPath -Raw | ConvertFrom-Json
    if ($shift.status -cne 'PREPARED_SHIFT_ADS_PASS_NOT_STA_OR_BOARD' -or
        $shift.run_id -cne $snapshot.run_id -or $shift.register_bits_per_fu -ne 38 -or
        $shift.fu_instances -ne 2 -or $shift.total_register_bits -ne 76 -or
        @($shift.registers).Count -ne 76 -or
        $shift.checker_sha256 -cne $snapshot.inputs.'scripts/audit_cpu_prepared_shift_ads.py' -or
        $shift.rtl_sha256 -cne $snapshot.inputs.'rtl/cpu/CoreTop.sv' -or
        $shift.input_snapshot_sha256 -cne (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $shift.netlist_sha256 -cne (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw 'Prepared-shift ADS evidence does not bind the frozen inputs and native netlist'
    }
    $null = Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
    Write-Output "PREPARED_SHIFT_PRE_PNR_ADS_PASS run=$($snapshot.run_id) bits=76 scope=ADS_ONLY"
}

# The normal Tcl calls this helper before dev_map/PnR. Keep the ICache result in
# this run's immutable evidence directory; finalization may validate, not invent it.
$icachePath = Join-Path $folder 'icache-pad-pre-pnr.json'
if (Test-Path -LiteralPath $icachePath) { throw 'Pre-PnR ICache result already exists for this run; refuse to reuse it' }
$icacheArgs = '"' + (Join-Path $root 'scripts/audit_icache_pad_ads.py') +
    '" --project-root "' + $root + '" --output "' + $icachePath + '"'
$icacheExit = [CpuSimulation.BoundedProcess]::Run($PythonPath, $icacheArgs, $root,
    (Join-Path $folder 'icache-pad-pre-pnr.stdout.log'), (Join-Path $folder 'icache-pad-pre-pnr.stderr.log'), 60)
if ($icacheExit -ne 0) { throw "Pre-PnR ICache ADS audit failed exit=$icacheExit; inspect $folder/icache-pad-pre-pnr.*" }
$icache = Get-Content -LiteralPath $icachePath -Raw | ConvertFrom-Json
Assert-IcachePadAdsEvidence $icache $snapshot `
    ((Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()) `
    ((Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant())
$null = Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
Write-Output "ICACHE_PRE_PNR_ADS_PASS run=$($snapshot.run_id) pairs=64 bits=128 ways=2 scope=ADS_ONLY"

if ((Get-Content -LiteralPath $cpuRtlPath -Raw).Contains('module PangoRobVaddrPad')) {
    $robPadPath=Join-Path $folder 'rob-vaddr-pad-pre-pnr.json'
    if(Test-Path -LiteralPath $robPadPath){throw 'ROB pad evidence already exists'}
    $robPadArgs='"'+(Join-Path $root 'scripts/audit_rob_vaddr_pad_ads.py')+'" --netlist "'+$netlist+'" --input-snapshot "'+$snapshotPath+'" --output "'+$robPadPath+'"'
    $robPadExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$robPadArgs,$root,
        (Join-Path $folder 'rob-vaddr-pad-pre-pnr.stdout.log'),(Join-Path $folder 'rob-vaddr-pad-pre-pnr.stderr.log'),60)
    if($robPadExit -ne 0){throw 'ROB virtual-address write-pad native retention failed'}
    $robPad=Get-Content -LiteralPath $robPadPath -Raw|ConvertFrom-Json
    if($robPad.status -cne 'PASS' -or $robPad.run_id -cne $snapshot.run_id -or
       $robPad.source_pairs -ne 16 -or $robPad.padded_di_pins -ne 64 -or $robPad.head_register_bits -ne 16 -or
       $robPad.checker_sha256 -cne $snapshot.inputs.'scripts/audit_rob_vaddr_pad_ads.py' -or
       $robPad.input_snapshot_sha256 -cne (Get-FileHash $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
       $robPad.netlist_sha256 -cne (Get-FileHash $netlist -Algorithm SHA256).Hash.ToLowerInvariant()){
        throw 'ROB write-pad/head retention evidence does not bind frozen native inputs'
    }
    $null=Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
    Write-Output 'ROB_VADDR_PAD_PRE_PNR_ADS_PASS pairs=16 di_pins=64 head_ffs=16 scope=ADS_ONLY'
}

# Shared word-input pads must survive before any implementation starts.
if (Test-FpgaVision32Profile $root) {
    $visionProofPath=Join-Path $folder 'cpu-clock-pre-pnr.json'
    if (!(Test-Path -LiteralPath $visionProofPath)) { throw 'Vision32 requires current native PE/cache/resource proof' }
    $visionProof=Get-Content -LiteralPath $visionProofPath -Raw|ConvertFrom-Json
    if ($visionProof.vision32_enabled -ne $true -or $visionProof.conv_resources.pe_apm -ne 32 -or
        !$visionProof.conv_resources.cache_mapping_proof -or
        $visionProof.audit_script_sha256 -cne $snapshot.inputs.'scripts/audit_cpu_dedicated_pll_ads.py') {
        throw 'Replacement vision32 physical cache/PE proof is missing'
    }
    if (Test-Path -LiteralPath (Join-Path $root 'config/vision32_cache_contract.json')) {
        $cache=$visionProof.conv_resources.cache_mapping_proof
        if ($cache.profile -cne 'bram_1024_128_sync_v1' -or $cache.weight_logical_bytes -ne 9216 -or
            $cache.weight_physical_capacity_bytes -ne 12288 -or $cache.weight_decoder_roots_proven -ne 4 -or
            $cache.accepted_write_data_bits_proven -ne 128 -or $cache.pe_weight_mux_bits_proven -ne 64 -or
            $cache.read_enable_roots_proven -ne 4 -or $cache.read_latency_cycles -ne 1 -or
            $cache.clock_domain -cne 'sys_clk' -or $cache.registered_bank_select -ne $true -or
            $visionProof.conv_resources.cache_profile_sha256 -cne $snapshot.inputs.'config/vision32_cache_contract.json' -or
            $visionProof.conv_resources.cache_checker_sha256 -cne $snapshot.inputs.'scripts/vision32_bram_cache_contract.py') {
            throw 'BRAM physical mapping proof does not bind the frozen profile/checker'
        }
    }
    Write-Output 'VISION32_NATIVE_PE_AND_CACHE_RETENTION_PASS legacy_conv_DMA_absent scope=ADS_ONLY'
}
if (!$pikafishOnly -and (Get-Content -LiteralPath (Join-Path $root 'rtl/mac_accel/MacAccelCore.v') -Raw).Contains('u_word_input_hold_lut')) {
    $weightPath=Join-Path $folder 'weight-pad-pre-pnr.json'
    if(Test-Path -LiteralPath $weightPath){throw 'Weight pad evidence already exists'}
    $weightArgs='"'+(Join-Path $root 'scripts/audit_mac_weight_pad_ads.py')+'" --netlist "'+$netlist+'" --input-snapshot "'+$snapshotPath+'" --output "'+$weightPath+'"'
    $weightExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$weightArgs,$root,
        (Join-Path $folder 'weight-pad-pre-pnr.stdout.log'),(Join-Path $folder 'weight-pad-pre-pnr.stderr.log'),60)
    if($weightExit -ne 0){throw 'Weight pad native ADS retention failed before PnR'}
    $weight=Get-Content -LiteralPath $weightPath -Raw|ConvertFrom-Json
    if($weight.status -cne 'PASS' -or $weight.run_id -cne $snapshot.run_id -or
       $weight.di_pins_checked -ne 1024 -or $weight.source_pairs -ne 16 -or
       $weight.checker_sha256 -cne $snapshot.inputs.'scripts/audit_mac_weight_pad_ads.py' -or
       $weight.input_snapshot_sha256 -cne (Get-FileHash $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant() -or
       $weight.netlist_sha256 -cne (Get-FileHash $netlist -Algorithm SHA256).Hash.ToLowerInvariant()){
        throw 'Weight pad evidence does not bind frozen native inputs'
    }
    $null=Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
    Write-Output 'WEIGHT_PAD_PRE_PNR_ADS_PASS pairs=16 di_pins=1024 scope=ADS_ONLY'
}

if (!(Test-FpgaVision32Profile $root) -and (Get-Content -Raw -LiteralPath (Join-Path $root 'rtl/mac_accel/mac_conv_weight_dma.v')).Contains('u_line_write_hold_lut')) {
    $convHoldPath=Join-Path $folder 'conv-weight-hold-pre-pnr.json'
    if(Test-Path -LiteralPath $convHoldPath){throw 'Convolution hold-pad evidence already exists'}
    $convHoldArgs='"'+(Join-Path $root 'scripts/audit_conv_weight_hold_ads.py')+'" --netlist "'+$netlist+'" --input-snapshot "'+$snapshotPath+'" --output "'+$convHoldPath+'"'
    $convHoldExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$convHoldArgs,$root,
        (Join-Path $folder 'conv-weight-hold-pre-pnr.stdout.log'),(Join-Path $folder 'conv-weight-hold-pre-pnr.stderr.log'),90)
    if($convHoldExit -ne 0){throw 'Convolution write hold pad did not survive native synthesis'}
    $convHold=Get-Content -Raw -LiteralPath $convHoldPath|ConvertFrom-Json
    if($convHold.status -cne 'PASS' -or $convHold.run_id -cne $snapshot.run_id -or
       $convHold.truth_cases -ne 4 -or $convHold.padded_di_pins -ne 4 -or
       $convHold.checker_sha256 -cne $snapshot.inputs.'scripts/audit_conv_weight_hold_ads.py' -or
       $convHold.netlist_sha256 -cne (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant() -or
       $convHold.input_snapshot_sha256 -cne (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()){
        throw 'Convolution hold-pad proof does not bind the frozen native inputs'
    }
    Write-Output 'CONV_WEIGHT_HOLD_PRE_PNR_ADS_PASS truth_cases=4 ram_di_pins=4 scope=ADS_ONLY'
}

if (Test-FpgaDedicatedLinearHoldProfile $root) {
    $linearHoldPath=Join-Path $folder 'pikafish-linear-hold-pre-pnr.json'
    $linearHoldArgs='"'+(Join-Path $root 'scripts/audit_pikafish_linear_hold_ads.py')+'" --netlist "'+$netlist+'" --input-snapshot "'+$snapshotPath+'" --output "'+$linearHoldPath+'"'
    $linearHoldExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$linearHoldArgs,$root,
        (Join-Path $folder 'pikafish-linear-hold.stdout.log'),(Join-Path $folder 'pikafish-linear-hold.stderr.log'),90)
    if($linearHoldExit -ne 0){throw 'Dedicated NNUE linear hold pads or actual RAM DI binding missing'}
    $linearHold=Get-Content -Raw -LiteralPath $linearHoldPath | ConvertFrom-Json
    if($linearHold.status -cne 'PASS' -or $linearHold.run_id -cne $snapshot.run_id -or
       $linearHold.pads -ne 16 -or $linearHold.padded_di_pins -ne 56 -or $linearHold.ram_di_pins_checked -ne 64 -or
       $linearHold.netlist_sha256 -cne (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash.ToLowerInvariant()){
        throw 'Dedicated NNUE hold proof does not bind the actual native run'
    }
    Write-Output 'PIKAFISH_LINEAR_HOLD_PRE_PNR_ADS_PASS pads=16 checked_di_pins=64 padded_di_pins=56 scope=ADS_ONLY'
}

$sdOwnerPath=Join-Path $folder 'sd-write-ownership-pre-pnr.json'
if(Test-Path -LiteralPath $sdOwnerPath){throw 'SD ownership evidence already exists'}
$sdOwnerArgs='"'+(Join-Path $root 'scripts/audit_sd_write_ownership_ads.py')+'" --netlist "'+$netlist+'" --input-snapshot "'+$snapshotPath+'" --output "'+$sdOwnerPath+'"'
$sdOwnerExit=[CpuSimulation.BoundedProcess]::Run($PythonPath,$sdOwnerArgs,$root,
    (Join-Path $folder 'sd-write-ownership-pre-pnr.stdout.log'),(Join-Path $folder 'sd-write-ownership-pre-pnr.stderr.log'),300)
if($sdOwnerExit -ne 0){throw 'SD RAM write ownership invariant proof failed before PnR'}
$sdOwner=Get-Content -LiteralPath $sdOwnerPath -Raw|ConvertFrom-Json
Assert-SdWriteOwnershipEvidence $sdOwner $snapshot `
    ((Get-FileHash $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()) `
    ((Get-FileHash $netlist -Algorithm SHA256).Hash.ToLowerInvariant())
$null=Read-FpgaActiveSnapshot $root ([datetime]::Parse($declared.started_utc))
Write-Output 'SD_WRITE_OWNERSHIP_PRE_PNR_ADS_PASS banks=2 mirrors=2 bits_per_view=4096 scope=ADS_ONLY'
& (Join-Path $root 'scripts/build_fpga.ps1') -CheckSdStorageOnly -PythonPath $PythonPath -SdOwnershipEvidencePath $sdOwnerPath
