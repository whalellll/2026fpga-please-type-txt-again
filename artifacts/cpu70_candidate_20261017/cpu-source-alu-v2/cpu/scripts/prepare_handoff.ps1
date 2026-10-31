$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$source = Join-Path $root 'coremark_test_soc/sim/coremark_ima'
& (Join-Path $PSScriptRoot 'verify_build_inputs.ps1') -GeneratedCpu -FirmwareDirectory $source
$manifest = Get-Content -LiteralPath "$source/manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.isa -ne 'rv32ima' -or $manifest.march -ne 'rv32ima_zicsr_zifencei' -or $manifest.abi -ne 'ilp32') {
    throw 'Fixed firmware must target RV32IMA/Zicsr/Zifencei with the ILP32 ABI.'
}
if ($manifest.compiler_target -ne 'riscv32-unknown-elf' -or $manifest.compiler_version -ne '16.2.0') {
    throw 'Rebuild contest firmware with riscv32-unknown-elf GCC 16.2.0 before preparing the handoff.'
}
$dest = Join-Path $root 'work/coremark-ima'
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($name in @('coremark.elf','coremark.bin','ram.hex','macros.txt','coremark_build_config.h')) {
    $original = Join-Path $source $name
    $expected = $manifest.files.$name
    if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -ne $expected) { throw "Fixed firmware hash mismatch: $name" }
    $file = Join-Path $dest $name
    if (!(Test-Path -LiteralPath $file)) { Copy-Item -LiteralPath $original -Destination $file }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $expected) {
        throw "Existing work firmware differs: $name. Preserve the experiment, then use a separate clean checkout."
    }
}
$targetManifest = Join-Path $dest 'manifest.json'
if (!(Test-Path -LiteralPath $targetManifest)) { Copy-Item -LiteralPath "$source/manifest.json" -Destination $targetManifest }
if ((Get-FileHash -LiteralPath $targetManifest -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath "$source/manifest.json" -Algorithm SHA256).Hash) {
    throw 'Existing work firmware manifest differs. Preserve the experiment, then use a separate clean checkout.'
}
Write-Output "FIXED_FIRMWARE_READY: verified RV32IMA/ILP32 $($manifest.cpu_hz) Hz $($manifest.evidence_class) firmware."
