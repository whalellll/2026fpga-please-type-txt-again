param([string]$Distro = 'chiplab_sim')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$artifacts = Join-Path $root 'artifacts'
$bootRoot = Join-Path $root 'linux\boot'
$modelCarrier = Join-Path $artifacts 'xiangqi_service.bin'
$expectedCarrierHash = '3f02e5dd7deff8d1a2647e070c088653e6804d98aa5db0b5974044a7cb0244f6'
$expectedModelHash = '9d075ad928f4bce1f52cf3f1466f12abe1d4fa37bdfda2fe6ae13d63de23fdda'
$modelOffset = 0x5950
$modelLength = 0x32bb0

if (!(Test-Path -LiteralPath $modelCarrier -PathType Leaf)) {
    throw "Missing validated model carrier: $modelCarrier"
}
$carrierHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modelCarrier).Hash.ToLowerInvariant()
if ($carrierHash -ne $expectedCarrierHash) {
    throw "Unexpected xiangqi_service.bin SHA-256: $carrierHash"
}

$carrierBytes = [IO.File]::ReadAllBytes($modelCarrier)
if ($carrierBytes.Length -lt $modelOffset + $modelLength) {
    throw 'Validated model carrier is shorter than the H128 model slice.'
}
$modelBytes = New-Object byte[] $modelLength
[Array]::Copy($carrierBytes, $modelOffset, $modelBytes, 0, $modelLength)
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $modelHash = (($sha256.ComputeHash($modelBytes) | ForEach-Object {
        $_.ToString('x2')
    }) -join '')
} finally {
    $sha256.Dispose()
}
if ($modelHash -ne $expectedModelHash) {
    throw "Unexpected extracted H128 model SHA-256: $modelHash"
}
if ([Text.Encoding]::ASCII.GetString($modelBytes, 0, 3) -ne 'XQ8' -or
    [BitConverter]::ToUInt32($modelBytes, 4) -ne 128 -or
    [BitConverter]::ToUInt32($modelBytes, 8) -ne 2 -or
    [BitConverter]::ToUInt32($modelBytes, 12) -ne 9 -or
    [BitConverter]::ToUInt32($modelBytes, 16) -ne 90) {
    throw 'Extracted model header is not the expected XQ8 H128 layout.'
}
New-Item -ItemType Directory -Force -Path $artifacts, $bootRoot | Out-Null
$artifactModel = Join-Path $artifacts 'xqmodel.bin'
$bootModel = Join-Path $bootRoot 'xqmodel.bin'
[IO.File]::WriteAllBytes($artifactModel, $modelBytes)
[IO.File]::WriteAllBytes($bootModel, $modelBytes)

$drive = $root.Substring(0, 1).ToLowerInvariant()
$tail = $root.Substring(2).Replace('\', '/')
$wslRoot = "/mnt/$drive$tail"
$command = @"
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd '$wslRoot'
mkdir -p artifacts
riscv64-unknown-elf-gcc -std=gnu99 -march=rv32im -mabi=ilp32 \
  -mcmodel=medany -mno-relax -msmall-data-limit=0 -mstrict-align -Os \
  -ffreestanding -fno-builtin -fno-common -ffunction-sections \
  -fdata-sections -Wall -Wextra -Werror -nostdlib -nostartfiles \
  -Wl,--gc-sections -Wl,--build-id=none \
  -Wl,-Map,artifacts/xiangqi_sd.map \
  -I sw/xiangqi/include -I sw/xiangqi -I sw/mac_accel -I sw/video \
  -T sw/xiangqi/link.ld \
  sw/xiangqi/start.S sw/xiangqi/model.S \
  sw/xiangqi/xiangqi_hdmi.c sw/xiangqi/xiangqi_fb_gui.c \
  sw/xiangqi/xiangqi_mouse_input.c sw/xiangqi/xiangqi_pikafish_link.c \
  sw/xiangqi/xiangqi_search.c sw/xiangqi/xiangqi_nnue_mac.c \
  sw/mac_accel/mac_accel_kernel.c -lgcc \
  -o artifacts/xiangqi_sd.elf
riscv64-unknown-elf-objcopy -O binary artifacts/xiangqi_sd.elf \
  artifacts/xiangqi_sd.bin
riscv64-unknown-elf-objdump -d -S artifacts/xiangqi_sd.elf \
  > artifacts/xiangqi_sd.disasm.txt
riscv64-unknown-elf-size -A artifacts/xiangqi_sd.elf \
  > artifacts/xiangqi_sd.size.txt
riscv64-unknown-elf-nm -n artifacts/xiangqi_sd.elf \
  > artifacts/xiangqi_sd.symbols.txt
grep -q '0f000000 A xq_model_start' artifacts/xiangqi_sd.symbols.txt
grep -q '0f032bb0 A xq_model_end' artifacts/xiangqi_sd.symbols.txt
"@
$command = $command.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "WSL Xiangqi SD build failed: $LASTEXITCODE"
}

$artifactGui = Join-Path $artifacts 'xiangqi_sd.bin'
$bootGui = Join-Path $bootRoot 'xiangqi.bin'
if ((Get-Item -LiteralPath $artifactGui).Length -gt 0x100000) {
    throw 'Xiangqi GUI image exceeds its 1 MiB DDR slot.'
}
Copy-Item -LiteralPath $artifactGui -Destination $bootGui -Force
$items = @(
    (Join-Path $artifacts 'xiangqi_sd.elf'),
    $artifactGui,
    $artifactModel,
    $bootGui,
    $bootModel
)
$hashLines = Get-FileHash -Algorithm SHA256 -LiteralPath $items | ForEach-Object {
    "$($_.Hash.ToLowerInvariant())  $($_.Path.Substring($root.Length + 1).Replace('\', '/'))"
}
[IO.File]::WriteAllLines(
    (Join-Path $artifacts 'xiangqi_sd.SHA256SUMS.txt'),
    $hashLines,
    [Text.UTF8Encoding]::new($false))

Get-Item -LiteralPath $bootGui, $bootModel |
    Select-Object FullName, Length, LastWriteTime
Get-FileHash -Algorithm SHA256 -LiteralPath $bootGui, $bootModel
