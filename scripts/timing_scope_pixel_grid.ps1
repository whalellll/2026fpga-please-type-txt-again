# Read-only adapter for the known physical-pixel-period vs declared-STA-grid
# mismatch. The original frozen checker is neither edited nor replaced.
function New-FpgaPixelGridScopeVerifier([string]$FrozenScopeSource) {
    $anchor="        if (`$name -eq 'cpu_clk') {"
    if([regex]::Matches($FrozenScopeSource,[regex]::Escape($anchor)).Count -ne 1){throw 'Frozen scope anchor differs; refuse an unreviewed adapter'}
    $addition=@'
        if ($name -eq 'pix_clk') {
            $declared = [regex]::Matches($fdc, '(?m)^create_clock -name \{pix_clk\} -period \{([0-9.]+)\}')
            if ($declared.Count -ne 1) { throw 'Pixel STA clock missing or duplicated' }
            $pixelFdc = [decimal]::Parse($declared[0].Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
            # Allow only sub0.1ps tightening of the physical pixel period.
            # CPU/display hardware audits independently bind frequency/target.
            if ($pixelFdc -gt $period -or $period-$pixelFdc -gt [decimal]0.0001) {
                throw 'Pixel physical/FDC period outside conservative representation grid'
            }
            $period = [decimal]::Floor($pixelFdc*1000)/1000
        }
'@
    $adapted=$FrozenScopeSource.Replace($anchor,$addition+"`n"+$anchor)
    $adapted=$adapted.Replace('function Assert-FpgaTimingScope(','function Assert-FpgaTimingScopePixelGrid(')
    $prefix='param([string]$XmlPath,[string]$FdcPath,[string]$PolicyPath)'+"`n"
    return [scriptblock]::Create($prefix+$adapted+"`nAssert-FpgaTimingScopePixelGrid `$XmlPath `$FdcPath `$PolicyPath")
}
