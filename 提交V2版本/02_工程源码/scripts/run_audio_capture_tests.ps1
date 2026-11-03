param([Parameter(Mandatory=$true)][string]$IcarusBin)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
$oldPath = $env:PATH
$env:PATH = $IcarusBin + ';' + $env:PATH
$out = Join-Path $root 'build/audio-capture-tests'
New-Item -ItemType Directory -Path $out -Force | Out-Null
Push-Location $root
try {
    foreach ($case in @(
        @('tb_audio_mmio','sim/tb_audio_mmio.v','TB_AUDIO_MMIO_PASS'),
        @('tb_i2s_audio','sim/tb_i2s_audio.v','TB_I2S_AUDIO_PASS'),
        @('tb_audio_fifo_order','sim/tb_audio_fifo_order.sv','AUDIO_FIFO_ORDER_PASS'),
        @('tb_audio_capture_chain','sim/tb_audio_capture_chain.sv','AUDIO_CAPTURE_CHAIN_PASS'))) {
        $image = Join-Path $out ($case[0] + '.vvp')
        & $iverilog -g2012 -Wall -s $case[0] -o $image `
            rtl/audio/audio_mmio.v rtl/audio/i2s_audio_duplex.v $case[1]
        if ($LASTEXITCODE -ne 0) { throw "Audio capture compile failed: $($case[0])" }
        $result = @(& $vvp $image 2>&1)
        $code = $LASTEXITCODE
        $result | Write-Output
        if ($code -ne 0 -or ($result -match '^\s*(ERROR:|FATAL:)') -or
            !($result -match ([regex]::Escape($case[2])))) {
            throw "Audio capture simulation failed: $($case[0])"
        }
    }
    Write-Output 'AUDIO_CAPTURE_TESTS_PASS'
} finally { Pop-Location; $env:PATH = $oldPath }
