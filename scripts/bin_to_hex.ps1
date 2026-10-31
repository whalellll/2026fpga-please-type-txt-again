param(
    [Parameter(Mandatory = $true)][string]$InputBin,
    [Parameter(Mandatory = $true)][string]$OutputHex,
    [int]$MemoryBytes = 131072
)

$ErrorActionPreference = 'Stop'
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $InputBin))
if ($bytes.Length -gt $MemoryBytes) {
    throw "Firmware is $($bytes.Length) bytes, larger than BRAM ($MemoryBytes bytes)."
}
if (($MemoryBytes % 4) -ne 0) {
    throw 'MemoryBytes must be a multiple of four.'
}

$lines = [string[]]::new($MemoryBytes / 4)
for ($word = 0; $word -lt $lines.Length; $word++) {
    $offset = $word * 4
    [uint32]$value = 0
    for ($lane = 0; $lane -lt 4; $lane++) {
        if (($offset + $lane) -lt $bytes.Length) {
            $value = $value -bor ([uint32]$bytes[$offset + $lane] -shl (8 * $lane))
        }
    }
    $lines[$word] = $value.ToString('x8')
}

$parent = Split-Path -Parent $OutputHex
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
[System.IO.File]::WriteAllLines($OutputHex, $lines,
    [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $($lines.Length) little-endian 32-bit words to $OutputHex"
