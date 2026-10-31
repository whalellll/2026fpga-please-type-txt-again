param(
    [Parameter(Mandatory=$true)][string]$WorkDirectory,
    [ValidateSet('baseline','candidate','combined')][string]$Variant = 'combined',
    [string]$PdsShell = 'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe',
    [ValidateRange(30,1800)][int]$TimeoutSeconds = 600
)
# ADS-only whole-SoC screening; never route, replace release outputs or program.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$work=[IO.Path]::GetFullPath($WorkDirectory)
$out=Join-Path $work $Variant
if(Test-Path -LiteralPath $out){throw "Use a new synthesis directory: $out"}
if(Get-Process pds_shell -ErrorAction SilentlyContinue){throw 'Another PDS shell is running'}
$snapshot=Get-Content -LiteralPath (Join-Path $root 'pds/build_snapshot.json') -Raw | ConvertFrom-Json
$inputs=@{}
foreach($name in $snapshot.inputs.PSObject.Properties.Name){
    $src=Join-Path $root $name
    if(!(Test-Path -LiteralPath $src -PathType Leaf)){throw "Missing declared build input: $src"}
    $dst=Join-Path $out $name
    New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst
}
if($Variant -eq 'baseline'){
    foreach($name in @('MacAccelCore.v','mac_accel_dma_kernel.v','mac_accel_axi_master32.v')){
        Copy-Item -LiteralPath (Join-Path $work "original/$name") -Destination (Join-Path $out "rtl/mac_accel/$name")
    }
}
if($Variant -eq 'candidate'){
    # Isolate the word-store resource tradeoff from the read-launch change.
    Copy-Item -LiteralPath (Join-Path $work 'original/mac_accel_axi_master32.v') -Destination (Join-Path $out 'rtl/mac_accel/mac_accel_axi_master32.v')
}
foreach($name in $snapshot.inputs.PSObject.Properties.Name){
    $inputs[$name]=(Get-FileHash -LiteralPath (Join-Path $out $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$inputs | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'input-hashes.json') -Encoding UTF8
$tcl=Get-Content -LiteralPath (Join-Path $out 'pds/soc.tcl') -Raw
if($tcl -match '(?m)^\s*(dev_map|pnr|bitgen)\b'){throw 'Expected ADS-only soc.tcl'}
if(!('CpuSimulation.BoundedProcess' -as [type])){Add-Type -Path (Join-Path $root 'scripts/bounded_process.cs')}
Write-Output "MAC_WEIGHT_WORD_SYNTH_START variant=$Variant owner=$PID timeout_s=$TimeoutSeconds stop=terminate_owner_process"
$code=[CpuSimulation.BoundedProcess]::Run($PdsShell,'-file soc.tcl',(Join-Path $out 'pds'),(Join-Path $out 'stdout.log'),(Join-Path $out 'stderr.log'),$TimeoutSeconds)
$log=[IO.File]::ReadAllText((Join-Path $out 'stdout.log'))+[IO.File]::ReadAllText((Join-Path $out 'stderr.log'))
if($code -ne 0 -or $log -match '(?im)^\s*(E:|ERROR:|FATAL:)'){throw "PDS failed: $out exit=$code"}
$snr=Join-Path $out 'pds/synthesize/soc_top.snr'
$text=Get-Content -LiteralPath $snr -Raw
$counts=@{}
foreach($field in @(@('luts','Total LUTs: (\d+)'),@('registers','Total Registers: (\d+)'),@('drm','Total DRM = ([0-9.]+)'),@('apm','Total APMs = ([0-9.]+)'),@('latches','Total Latches: (\d+)'))){
    $match=[regex]::Match($text,$field[1])
    if(!$match.Success){throw "Missing resource count: $($field[0])"}
    $counts[$field[0]]=[double]::Parse($match.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)
}
$result=[ordered]@{variant=$Variant;scope='whole_soc_ads_only';luts=$counts.luts;registers=$counts.registers;drm=$counts.drm;apm=$counts.apm;latches=$counts.latches;report_sha256=(Get-FileHash -LiteralPath $snr -Algorithm SHA256).Hash.ToLowerInvariant();inputs_sha256=(Get-FileHash -LiteralPath (Join-Path $out 'input-hashes.json') -Algorithm SHA256).Hash.ToLowerInvariant()}
if(!$result.luts -or $result.latches){throw 'Missing resource count or inferred latches'}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8
$result | ConvertTo-Json -Compress
