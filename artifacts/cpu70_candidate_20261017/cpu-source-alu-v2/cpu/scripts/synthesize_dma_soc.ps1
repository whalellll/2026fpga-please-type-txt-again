param(
    [string]$Config = (Join-Path $PSScriptRoot '../toolchain.local.json'),
    [double]$CpuPeriodNs = 10.0,
    [double]$DdrPeriodNs = 10.0,
    [double]$PixelPeriodNs = 13.5
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$settings = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$rtl = @(
    'generated/core/CoreTop.sv',
    'coremark_test_soc/rtl/cpu_top.v', 'coremark_test_soc/rtl/cpu_sd_dma_top.v',
    'coremark_test_soc/rtl/axi_1x2_sd.v', 'coremark_test_soc/rtl/axi_1x2_dma.v',
    'coremark_test_soc/rtl/axi_2x1_arbiter.v', 'coremark_test_soc/rtl/sd_axi_mmio.v',
    'coremark_test_soc/rtl/sd_native_mmio.v', 'coremark_test_soc/rtl/dma_axi_mmio.v',
    'coremark_test_soc/rtl/dma_axi_master32.v', 'coremark_test_soc/rtl/memcpy_dma_top.v',
    'coremark_test_soc/rtl/video_fb_dma.v', 'coremark_test_soc/rtl/video_fb_mmio.v',
    'coremark_test_soc/rtl/camera_frame_writer.v',
    'coremark_test_soc/rtl/camera_buffer_control.v', 'coremark_test_soc/rtl/camera_mmio.v',
    'coremark_test_soc/rtl/axi_ddr_cdc.v',
    'coremark_test_soc/rtl/ddr_native_read_arbiter.v',
    'coremark_test_soc/rtl/ddr_native_write_arbiter.v',
    'coremark_test_soc/ip/camera_line_buffer/camera_line_buffer.v',
    'coremark_test_soc/ip/camera_line_buffer/rtl/ipm2l_sdpram_v1_10_camera_line_buffer.v',
    'coremark_test_soc/rtl/cpu_all_dma_top.v'
)
foreach ($file in $rtl) {
    if (!(Test-Path -LiteralPath (Join-Path $root $file))) { throw "Missing $file" }
}
$stageRoot = [IO.Path]::GetFullPath($settings.PdsStageRoot)
$stage = Join-Path $stageRoot ('cpu-dma-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
if ($stage -match '[^\x20-\x7E]') { throw 'PDS staging path must be ASCII' }
New-Item -ItemType Directory -Path "$stage/scripts","$stage/work/scripts" -Force | Out-Null
foreach ($file in $rtl) {
    Copy-Item -LiteralPath (Join-Path $root $file) -Destination $stage
}
Copy-Item -LiteralPath "$root/scripts/meminit" -Destination "$stage/scripts" -Recurse
Copy-Item -LiteralPath "$root/scripts/meminit" -Destination "$stage/work/scripts" -Recurse

$project = Get-Content -LiteralPath "$root/coremark_test_soc/pds/coremark_test_soc.pds" -Raw
$project = $project.Replace('../../generated/core/CoreTop.sv', 'CoreTop.sv')
$project = $project.Replace('../rtl/coremark_soc_top.v', 'cpu_all_dma_top.v')
$project = $project.Replace('coremark_soc_top', 'cpu_all_dma_top')
$project = $project.Replace('coremark_test_soc.fdc', 'cpu_all_dma_soc.fdc')
foreach ($file in @('axi_bram_uart.v', 'uart_tx_fifo.v')) {
    $pattern = '(?s)\s*\(_file "../rtl/' + [regex]::Escape($file) + '"\s*\(_format verilog\)\s*\(_timespec "[^"]+"\)\s*\)'
    $project = [regex]::Replace($project, $pattern, '')
}
$entries = foreach ($file in $rtl | Select-Object -Skip 1 | Select-Object -SkipLast 1) {
    $baseName = [IO.Path]::GetFileName($file)
    "                (_file `"$baseName`"`n                    (_format verilog)`n                    (_timespec `"2026-09-24T00:00:00`")`n                )"
}
$needle = '                (_file "cpu_all_dma_top.v"'
if (!$project.Contains($needle)) { throw 'PDS top source entry missing' }
$project = $project.Replace($needle, ($entries -join "`n") + "`n" + $needle)
Set-Content -LiteralPath "$stage/cpu_all_dma_soc.pds" -Value $project -Encoding ascii
$fdc = @(
    "create_clock -name cpu_clk -period $CpuPeriodNs [get_ports {aclk}]",
    "create_clock -name ddr_clk -period $DdrPeriodNs [get_ports {ddr_clk}]",
    "create_clock -name pixel_clk -period $PixelPeriodNs [get_ports {pix_clk}]",
    "create_clock -name camera_pixel_clk -period $PixelPeriodNs [get_ports {camera_pixel_clk}]"
)
Set-Content -LiteralPath "$stage/cpu_all_dma_soc.fdc" -Value $fdc -Encoding ascii

$logRoot = Join-Path $root 'work/logs/pds-dma'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Set-Content -LiteralPath "$logRoot/stage.txt" -Value $stage
Get-FileHash -LiteralPath ($rtl | ForEach-Object { Join-Path $root $_ }) |
    Format-Table -AutoSize | Out-File "$logRoot/rtl-sha256.txt"
Push-Location -LiteralPath $stage
try {
    & $settings.PdsShell -project cpu_all_dma_soc.pds -work_dir work -run synthesize *> "$logRoot/synthesis.log"
    $rc = $LASTEXITCODE
    $log = Get-Content -LiteralPath "$logRoot/synthesis.log" -Raw
    if ($rc -ne 0 -or $log -match '(?m)^E:|Program Error Out|Parsing ERROR|Cannot open specified data file') {
        throw 'PDS synthesis failed; inspect work/logs/pds-dma/synthesis.log'
    }
    if (!$log.Contains('Process "Synthesize" done.')) {
        throw 'PDS synthesis completion marker missing'
    }
    $report = @(Get-ChildItem -LiteralPath $stage -Filter 'cpu_all_dma_top.snr' -Recurse)
    if ($report.Count -ne 1) { throw 'Expected exactly one synthesis report' }
    Copy-Item -LiteralPath $report[0].FullName -Destination "$logRoot/cpu_all_dma_top.snr"
} finally { Pop-Location }



