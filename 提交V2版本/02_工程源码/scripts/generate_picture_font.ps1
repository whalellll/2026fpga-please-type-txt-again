param([string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
if (!$OutputPath) { $OutputPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'linux/vision/xq_picture_font.h' }
Add-Type -AssemblyName System.Drawing
$glyphPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'linux/vision/picture_glyphs.txt'
$characters = [IO.File]::ReadAllText($glyphPath,[Text.Encoding]::UTF8)
$codes = @($characters.ToCharArray() | ForEach-Object { if ([int]$_ -gt 127) { [int]$_ } } | Sort-Object -Unique)
$bitmap = [Drawing.Bitmap]::new(16,16)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$font = [Drawing.Font]::new('Microsoft YaHei',11,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Pixel)
$format = [Drawing.StringFormat]::GenericTypographic
$graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
$lines = [Collections.Generic.List[string]]::new()
$lines.Add('/* Static GUI glyph raster, Microsoft YaHei 11 px; generated with')
$lines.Add(' * scripts/generate_picture_font.ps1. No font program is embedded. */')
$lines.Add('#ifndef XQ_PICTURE_FONT_H')
$lines.Add('#define XQ_PICTURE_FONT_H')
$lines.Add('#include <stdint.h>')
$lines.Add('static const struct { uint16_t code; uint16_t rows[16]; } xqp_glyphs[] = {')
try {
 foreach ($code in $codes) {
  $graphics.Clear([Drawing.Color]::Black)
  $graphics.DrawString([string][char]$code,$font,[Drawing.Brushes]::White,1,0,$format)
  $rows = for ($y=0; $y -lt 16; $y++) {
   $bits=0
   for ($x=0; $x -lt 16; $x++) {
    if ($bitmap.GetPixel($x,$y).R -ge 128) { $bits=$bits -bor (1 -shl (15-$x)) }
   }
   '0x{0:x4}' -f $bits
  }
  $lines.Add(('    {{0x{0:x4}, {{{1}}}}},' -f $code,($rows -join ',')))
 }
 $lines.Add('};')
 $lines.Add('#endif')
 [IO.File]::WriteAllLines([IO.Path]::GetFullPath($OutputPath),$lines,[Text.UTF8Encoding]::new($false))
} finally { $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose() }
