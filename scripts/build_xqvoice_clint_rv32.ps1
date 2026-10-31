param(
    [string]$Distro = 'pikafish-verify',
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputPath) {
    $OutputPath = Join-Path $root 'build\xqvoice\out'
}
[IO.Directory]::CreateDirectory($OutputPath) | Out-Null

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$wslRoot = Convert-ToWslPath $root
$wslOutput = Convert-ToWslPath $OutputPath
$command = @"
set -eu
test -x /opt/toolchain/bin/riscv32-linux-musl-gcc
mkdir -p '$wslOutput'
/opt/toolchain/bin/riscv32-linux-musl-gcc \
  -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
  -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
  -static -Wl,--gc-sections -Wall -Wextra -Werror \
  -I'$wslRoot/linux/voice' -I'$wslRoot/linux/audio' \
  '$wslRoot/linux/voice/xqvoice_daemon.c' \
  '$wslRoot/linux/voice/xqvoice_client.c' \
  '$wslRoot/linux/voice/xqvoice_protocol.c' \
  '$wslRoot/linux/voice/xqvoice_model.c' \
  '$wslRoot/linux/voice/xqvoice_features.c' \
  '$wslRoot/linux/voice/xqvoice_accel.c' \
  '$wslRoot/linux/voice/xqvoice_assembler.c' \
  -o '$wslOutput/xqvoice'
/opt/toolchain/bin/riscv32-linux-musl-gcc \
  -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
  -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
  -static -Wl,--gc-sections -Wall -Wextra -Werror \
  -I'$wslRoot/linux/voice' \
  '$wslRoot/linux/voice/xqvoice_send.c' \
  '$wslRoot/linux/voice/xqvoice_client.c' \
  '$wslRoot/linux/voice/xqvoice_protocol.c' \
  -o '$wslOutput/xqvoice-send'
/opt/toolchain/bin/riscv32-linux-musl-gcc \
  -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 \
  -static -Wall -Wextra -Werror -I'$wslRoot/linux/audio' \
  '$wslRoot/linux/audio/xqaudio_capture.c' -o '$wslOutput/xqaudio-capture'
/opt/toolchain/bin/riscv32-linux-musl-gcc \
  -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
  -static -pthread -Wall -Wextra -Werror \
  -I'$wslRoot/linux/voice' -I'$wslRoot/linux/audio' \
  '$wslRoot/linux/voice/xqvoice_accel_bench.c' \
  '$wslRoot/linux/voice/xqvoice_accel.c' \
  '$wslRoot/linux/voice/xqvoice_features.c' \
  '$wslRoot/linux/voice/xqvoice_bench_clock.c' \
  '$wslRoot/linux/pikafish/nnue_clint_clock.c' \
  -Wl,--wrap=clock_gettime,--wrap=clock_getres \
  -o '$wslOutput/xqvoice-accel-bench'
/opt/toolchain/bin/riscv32-linux-musl-strip \
  '$wslOutput/xqvoice' '$wslOutput/xqvoice-send' '$wslOutput/xqaudio-capture' '$wslOutput/xqvoice-accel-bench'
file '$wslOutput/xqvoice' '$wslOutput/xqvoice-send' '$wslOutput/xqaudio-capture' '$wslOutput/xqvoice-accel-bench'
printf '%s\n' XQVOICE_RV32_BUILD_PASS
"@
$command = $command.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'XQVoice RV32 build failed'
}

Get-Item -LiteralPath (Join-Path $OutputPath 'xqvoice'),
    (Join-Path $OutputPath 'xqvoice-send'),
    (Join-Path $OutputPath 'xqaudio-capture') | Select-Object FullName, Length
