param(
    [string]$InputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'linux\boot\soc.dtb'),
    [string]$OutputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'linux\boot\soc.dtb')
)

$ErrorActionPreference = 'Stop'
$inputFull = [IO.Path]::GetFullPath($InputPath)
$outputFull = [IO.Path]::GetFullPath($OutputPath)
$bytes = [IO.File]::ReadAllBytes($inputFull)
$oldText = 'console=liteuart earlycon=liteuart,0x1fe001e0 rootwait root=/dev/ram0 loglevel=8'
$newText = 'console=liteuart0 earlycon root=/dev/ram0 loglevel=8 clocksource=jiffies'
$old = [Text.Encoding]::ASCII.GetBytes($oldText)
if ($newText.Length -gt $oldText.Length) { throw 'Stable bootargs do not fit in the DTB property' }
$new = [Text.Encoding]::ASCII.GetBytes($newText.PadRight($oldText.Length))

$match = -1
for ($i = 0; $i -le $bytes.Length - $old.Length; $i++) {
    $same = $true
    for ($j = 0; $j -lt $old.Length; $j++) {
        if ($bytes[$i + $j] -ne $old[$j]) { $same = $false; break }
    }
    if ($same) { $match = $i; break }
}

if ($match -lt 0) {
    $already = [Text.Encoding]::ASCII.GetBytes($newText)
    for ($i = 0; $i -le $bytes.Length - $already.Length; $i++) {
        $same = $true
        for ($j = 0; $j -lt $already.Length; $j++) {
            if ($bytes[$i + $j] -ne $already[$j]) { $same = $false; break }
        }
        if ($same) {
            Write-Host "DTB already contains stable bootargs: $outputFull"
            exit 0
        }
    }
    throw 'Original bootargs marker not found in DTB'
}

[Array]::Copy($new, 0, $bytes, $match, $new.Length)
[IO.File]::WriteAllBytes($outputFull, $bytes)
Write-Host "Wrote stable DTB: $outputFull ($($bytes.Length) bytes)"
