param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')

function Remove-GeneratedPath([string]$Relative) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $Relative))
    if (!$path.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup escaped project root' }
    if (!(Test-Path -LiteralPath $path)) { return }
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked cleanup target: $path" }
    if ($item.PSIsContainer) {
        $links = @(Get-ChildItem -LiteralPath $path -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        })
        if ($links.Count) { throw "Refusing cleanup through a linked child: $path" }
        if ($DryRun) { Write-Output "WOULD_REMOVE $Relative"; return }
        Remove-Item -LiteralPath $path -Recurse -Force
    } else {
        if ($DryRun) { Write-Output "WOULD_REMOVE $Relative"; return }
        Remove-Item -LiteralPath $path -Force
    }
}

foreach ($directory in @('artifacts/bootloader_obj', 'artifacts/hello_obj', 'artifacts/mac_selftest_obj',
    'artifacts/mac_benchmark_obj', 'artifacts/xiangqi_sparse_eval_obj',
    'artifacts/xiangqi_fb_demo_obj', 'sim/__pycache__')) {
    Remove-GeneratedPath $directory
}
# Firmware, ROMs, bitstreams, PDS native reports and test evidence may be
# current release inputs. They are intentionally outside this cleanup list.
if ($DryRun) { Write-Output 'SOC_GENERATED_CLEAN_DRY_RUN_PASS' }
else { Write-Output 'SOC_GENERATED_CLEAN_PASS' }
