param(
    [string]$OutputPath,
    [string]$PreviewPath,
    [string]$LogoOutputPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
if (!$OutputPath) { $OutputPath = Join-Path $root 'rtl\video\header_bitmap.hex' }
if (!$PreviewPath) { $PreviewPath = Join-Path $root 'artifacts\hdmi_header_preview.png' }
if (!$LogoOutputPath) { $LogoOutputPath = Join-Path $root 'rtl\video\header_logo_rgb332.hex' }

$width = 384
$height = 64
$bitmap = New-Object Drawing.Bitmap $width, $height,
    ([Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([Drawing.Color]::Black)
$graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$white = [Drawing.Brushes]::White
$black = [Drawing.Brushes]::Black

# Draw a self-contained terminal icon.  Broad filled shapes survive RGB332
# quantization and avoid an external logo or trademark dependency.
$screenBrush = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(12, 32, 52))
$barBrush = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(25, 157, 216))
$cyanPen = New-Object Drawing.Pen ([Drawing.Color]::FromArgb(64, 210, 255)), 3
$whitePen = New-Object Drawing.Pen ([Drawing.Color]::White), 3
$graphics.FillRectangle($screenBrush, 9, 6, 62, 47)
$graphics.DrawRectangle($cyanPen, 9, 6, 61, 46)
$graphics.FillRectangle($barBrush, 11, 8, 58, 10)
$graphics.DrawLine($whitePen, 24, 27, 31, 33)
$graphics.DrawLine($whitePen, 31, 33, 24, 39)
$graphics.DrawLine($whitePen, 37, 39, 51, 39)
$graphics.FillRectangle($barBrush, 35, 53, 10, 4)
$graphics.FillRectangle($barBrush, 27, 57, 26, 3)

$consoleFont = New-Object Drawing.Font 'Segoe UI', 20,
    ([Drawing.FontStyle]::Bold), ([Drawing.GraphicsUnit]::Pixel)
$cnFont = New-Object Drawing.Font 'Noto Sans SC Medium', 25,
    ([Drawing.FontStyle]::Regular), ([Drawing.GraphicsUnit]::Pixel)
if ($consoleFont.Name -cne 'Segoe UI' -or $cnFont.Name -cne 'Noto Sans SC Medium') {
    $actualFonts = "$($consoleFont.Name) / $($cnFont.Name)"
    $cnFont.Dispose()
    $consoleFont.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
    throw "HDMI redraw requires exact Segoe UI and Noto Sans SC Medium fonts; System.Drawing selected $actualFonts. Keep the tracked HEX files or install the required fonts."
}
$graphics.DrawString('CONSOLE', $consoleFont, $white, 82, 18)
$title = [string]([char]0x8bf7) + [char]0x8f93 + [char]0x5165 +
    [char]0x6587 + [char]0x672c
$graphics.DrawString($title, $cnFont, $white, 195, 15)
$graphics.FillRectangle($white, 82, 49, 260, 2)

$outDir = Split-Path -Parent ([IO.Path]::GetFullPath($OutputPath))
$previewDir = Split-Path -Parent ([IO.Path]::GetFullPath($PreviewPath))
$logoOutDir = Split-Path -Parent ([IO.Path]::GetFullPath($LogoOutputPath))
[IO.Directory]::CreateDirectory($outDir) | Out-Null
[IO.Directory]::CreateDirectory($previewDir) | Out-Null
[IO.Directory]::CreateDirectory($logoOutDir) | Out-Null

$lines = New-Object 'Collections.Generic.List[string]'
for ($y = 0; $y -lt $height; $y++) {
    for ($byteX = 0; $byteX -lt ($width / 8); $byteX++) {
        $value = 0
        for ($bit = 0; $bit -lt 8; $bit++) {
            $pixel = $bitmap.GetPixel(($byteX * 8) + $bit, $y)
            if (($pixel.R + $pixel.G + $pixel.B) -ge 192) {
                $value = $value -bor (1 -shl (7 - $bit))
            }
        }
        $lines.Add($value.ToString('x2'))
    }
}
[IO.File]::WriteAllLines([IO.Path]::GetFullPath($OutputPath), $lines,
    (New-Object Text.UTF8Encoding($false)))

# One RGB332 byte per pixel for the 80x64 terminal-icon region.
$logoLines = New-Object 'Collections.Generic.List[string]'
for ($y = 0; $y -lt $height; $y++) {
    for ($x = 0; $x -lt 80; $x++) {
        $pixel = $bitmap.GetPixel($x, $y)
        $rgb332 = (($pixel.R -shr 5) -shl 5) -bor
                  (($pixel.G -shr 5) -shl 2) -bor
                  ($pixel.B -shr 6)
        $logoLines.Add(([byte]$rgb332).ToString('x2'))
    }
}
[IO.File]::WriteAllLines([IO.Path]::GetFullPath($LogoOutputPath), $logoLines,
    (New-Object Text.UTF8Encoding($false)))
$bitmap.Save([IO.Path]::GetFullPath($PreviewPath),
    [Drawing.Imaging.ImageFormat]::Png)

$cnFont.Dispose()
$consoleFont.Dispose()
$screenBrush.Dispose()
$barBrush.Dispose()
$cyanPen.Dispose()
$whitePen.Dispose()
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "HDMI header bitmap: $OutputPath ($($lines.Count) bytes)"
Write-Host "HDMI console icon RGB332: $LogoOutputPath ($($logoLines.Count) bytes)"
Write-Host "HDMI header preview: $PreviewPath"
