param([string]$ToolchainRoot = '')

# Native-toolchain build of the bare-metal Xiangqi chess GUI image
# (xiangqi.bin) and extraction of the H128 model (xqmodel.bin) from the
# validated opaque carrier. Produces the two MicroSD payloads consumed by
# the bootloader `xqboot` command. The historical WSL entry
# build_xiangqi_sd_wsl.ps1 required a chiplab_sim distro; this script uses
# the same verified native riscv32-unknown-elf compiler as all v2 firmware.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$root = Split-Path -Parent $PSScriptRoot
$artifacts = Join-Path $root 'artifacts'
$bootRoot = Join-Path $root 'linux\boot'
$modelCarrier = Join-Path $root 'artifacts\xiangqi_service.bin'
if (!(Test-Path -LiteralPath $modelCarrier -PathType Leaf)) {
    # The tracked fixed input under prebuilt/ is the same opaque carrier.
    $modelCarrier = Join-Path $root 'prebuilt\xiangqi_service.bin'
}
$expectedCarrierHash = '3f02e5dd7deff8d1a2647e070c088653e6804d98aa5db0b5974044a7cb0244f6'
$expectedModelHash = '9d075ad928f4bce1f52cf3f1466f12abe1d4fa37bdfda2fe6ae13d63de23fdda'
$modelOffset = 0x5950
$modelLength = 0x32bb0

$toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$gcc = $toolchain.gcc
$objcopy = $toolchain.objcopy
$objdump = $toolchain.objdump
$size = $toolchain.size

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

$cpuOriginalPath = $env:PATH
try {
    $env:PATH = "$($toolchain.Root);$env:PATH"
    Push-Location -LiteralPath $root
    $sources = @(
        'sw/xiangqi/start.S', 'sw/xiangqi/model.S',
        'sw/xiangqi/xiangqi_hdmi.c', 'sw/xiangqi/xiangqi_fb_gui.c',
        'sw/xiangqi/xiangqi_mouse_input.c', 'sw/xiangqi/xiangqi_pikafish_link.c',
        'sw/xiangqi/xiangqi_search.c', 'sw/xiangqi/xiangqi_nnue_mac.c',
        'sw/mac_accel/mac_accel_kernel.c'
    )
    & $gcc '-std=gnu99' "-march=$CpuMarch" "-mabi=$CpuAbi" `
        '-mcmodel=medany' '-mno-relax' '-msmall-data-limit=0' '-mstrict-align' '-Os' `
        '-ffreestanding' '-fno-builtin' '-fno-common' '-ffunction-sections' `
        '-fdata-sections' '-Wall' '-Wextra' '-Werror' '-nostdlib' '-nostartfiles' `
        '-Wl,--gc-sections' '-Wl,--build-id=none' `
        '-Wl,-Map,artifacts/xiangqi_sd.map' `
        '-I' 'sw/xiangqi/include' '-I' 'sw/xiangqi' '-I' 'sw/mac_accel' '-I' 'sw/video' `
        '-T' 'sw/xiangqi/link.ld' `
        @sources '-lgcc' `
        '-o' 'artifacts/xiangqi_sd.elf'
    if ($LASTEXITCODE -ne 0) { throw "Xiangqi SD build failed: $LASTEXITCODE" }
    & $objcopy '-O' 'binary' 'artifacts/xiangqi_sd.elf' 'artifacts/xiangqi_sd.bin'
    if ($LASTEXITCODE -ne 0) { throw 'objcopy failed' }
    & $objdump '-d' '-S' 'artifacts/xiangqi_sd.elf' |
        Out-File -FilePath 'artifacts/xiangqi_sd.disasm.txt' -Encoding ascii
    & $size '-A' 'artifacts/xiangqi_sd.elf' |
        Out-File -FilePath 'artifacts/xiangqi_sd.size.txt' -Encoding ascii
    & $toolchain.nm -n 'artifacts/xiangqi_sd.elf' |
        Out-File -FilePath 'artifacts/xiangqi_sd.symbols.txt' -Encoding ascii
} finally {
    Pop-Location
    $env:PATH = $cpuOriginalPath
}

$symbols = Get-Content -LiteralPath (Join-Path $root 'artifacts\xiangqi_sd.symbols.txt')
if (!(@($symbols | Where-Object { $_ -match '^0f000000 A xq_model_start$' }).Count)) {
    throw 'xq_model_start symbol missing or moved'
}
if (!(@($symbols | Where-Object { $_ -match '^0f032bb0 A xq_model_end$' }).Count)) {
    throw 'xq_model_end symbol missing or moved'
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
Write-Output 'XIANGQI_SD_BUILD_PASS'
