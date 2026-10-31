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
if (!(Test-Path -LiteralPath $netlist -PathType Leaf)) { throw 'Pre-PnR ADS netlist is missing' }
if (-not ('CpuSimulation.BoundedProcess' -as [type])) { Add-Type -Path (Join-Path $root 'scripts/bounded_process.cs') }
$arguments = '"' + (Join-Path $root 'scripts/audit_cpu_ads.py') + '" "' + $netlist +
    '" --input-snapshot "' + $snapshotPath + '" --output "' + $resultPath + '"'
$exitCode = [CpuSimulation.BoundedProcess]::Run($PythonPath, $arguments, $root,
    (Join-Path $folder 'cpu-pre-pnr.stdout.log'), (Join-Path $folder 'cpu-pre-pnr.stderr.log'), 300)
if ($exitCode -ne 0) { throw "Pre-PnR CPU ADS audit failed exit=$exitCode; inspect $folder/cpu-pre-pnr.*" }
$result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
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
        '" --resources "'+(Join-Path $root 'pds/synthesize/soc_top.snr')+'" --fdc "'+(Join-Path $root 'pds/soc.fdc')+'" --output "'+$clockOutput+'"'
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
