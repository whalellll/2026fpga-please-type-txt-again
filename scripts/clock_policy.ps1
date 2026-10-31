# Reviewed PG2L100H GPLL search window. Hardware legality is not a timing pass.
# PDS 2022.2-SP6.4 UG041001_PLL_IP: ODIV3 is integer 1..128;
# The video/SYS PLL remains at 891 MHz. The dedicated CPU profile uses
# IDIV=1, MDIV=2, FDIV=15.75 (legal n/8 feedback), ODIV3=12.
function Assert-SocDisplayClockHardware([string]$Root, $Clock) {
    $display = Get-Content -LiteralPath (Join-Path $Root 'config/display.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $top = [IO.File]::ReadAllText((Join-Path $Root 'rtl/soc/soc_top.v'))
    $pll = [IO.File]::ReadAllText((Join-Path $Root 'rtl/video/pll_video.v'))
    $totalPixels = ($display.width + $display.h_front + $display.h_sync + $display.h_back) *
                   ($display.height + $display.v_front + $display.v_sync + $display.v_back)
    $expectedDivider = if ($display.profile -ceq '1080p30') { 12 } elseif ($display.profile -ceq '1080p60') { 6 } else { throw 'Unsupported native display profile' }
    $expectedHz = if ($expectedDivider -eq 12) { 74250000 } else { 148500000 }
    $expectedRefresh = if ($expectedDivider -eq 12) { 30 } else { 60 }
    $expectedPeriod = if ($expectedDivider -eq 12) { '13.468' } else { '6.734' }
    if ($display.width -ne 1920 -or $display.height -ne 1080 -or
        $display.pixel_divisor -ne $expectedDivider -or $display.pixel_hz -ne $expectedHz -or
        $display.refresh_hz -ne $expectedRefresh -or
        $display.video_pll_vco_hz -ne $Clock.pll_vco_hz -or
        $display.pixel_hz * $display.pixel_divisor -ne $Clock.pll_vco_hz -or
        $totalPixels * $display.refresh_hz -ne $display.pixel_hz) {
        throw 'Display clock intent differs from its native profile or the fixed video/SYS VCO'
    }
    if ([regex]::Matches($top, '\.PIXEL_DIVISOR\s*\(\s*'+$expectedDivider+'\s*\)').Count -ne 1 -or
        $pll -notmatch 'STATIC_DUTY0\s*=\s*PIXEL_DIVISOR\s*;' -or
        $pll -notmatch 'STATIC_RATIO0\s*=\s*PIXEL_DIVISOR \* 1\.0\s*;') {
        throw 'Pixel divider or duty differs from config/display.json'
    }
    $scope = Get-Content -LiteralPath (Join-Path $Root 'config/timing_scope_baseline.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([math]::Abs([double]$scope.clocks.pix_clk.period_ns - 1e9 / $display.pixel_hz) -gt 0.0001) {
        throw 'STA pixel clock scope differs from the requested pixel output'
    }
    $fdc = [IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc'))
    if ([regex]::Matches($fdc, 'create_clock -name \{pix_clk\} -period \{'+[regex]::Escape($expectedPeriod)+'\} \[get_nets \{u_video_pll/clkout0\}\]').Count -ne 1) {
        throw 'FDC pixel period differs from the selected native profile'
    }
}

function Get-SocCpuClockMode($Clock) {
    $source=$Clock.cpu_clock_source
    if (!$source -or $source -ceq 'video891') { return 0 }
    if ($source -ceq 'dedicated850p5') { return 1 }
    if ($source -ceq 'dedicated675') { return 2 }
    if ($source -ceq 'dedicated800') { return 3 }
    if ($source -ceq 'dedicated1080frac') { return 4 }
    if ($source -ceq 'dedicated1147p5frac') { return 5 }
    if ($source -ceq 'dedicated945frac') { return 6 }
    throw 'Unsupported CPU clock source'
}
function Get-SocCpuPllVcoHz($Clock) {
    if ((Get-SocCpuClockMode $Clock) -eq 6) { return [decimal]945000000 }
    if ((Get-SocCpuClockMode $Clock) -eq 5) { return [decimal]1147500000 }
    if ((Get-SocCpuClockMode $Clock) -eq 4) { return [decimal]1080000000 }
    if ((Get-SocCpuClockMode $Clock) -eq 3) { return [decimal]800000000 }
    if ((Get-SocCpuClockMode $Clock) -eq 2) { return [decimal]675000000 }
    if ((Get-SocCpuClockMode $Clock) -eq 1) { return [decimal]850500000 }
    return [decimal]891000000
}
function Get-SocCpuConstraintPeriodNs($Clock) {
    # Exact70 MHz physical clock; tighten by3.714ps, common273 CPU/193 SYS cycles.
    if ((Get-SocCpuClockMode $Clock) -eq 6) { return [decimal]14.282 }
    # 85MHz physical period=200/17ns; strict11.760ns has481:280 common expansion with SYS.
    if ((Get-SocCpuClockMode $Clock) -eq 5) { return [decimal]11.760 }
    # 80MHz is125MHz/5*32/10; tighten12.5ns by5ps for exact962/595 expansion.
    if ((Get-SocCpuClockMode $Clock) -eq 4 -and $Clock.cpu_divisor -eq 36) { return [decimal]16.650 }
    if ((Get-SocCpuClockMode $Clock) -in @(3,4)) { return [decimal]12.495 }
    # Physical CPU75 remains 675MHz/9. PDS rounds periods to a 1ps grid;
    # 13.333ns and 20.202ns need >1000 cycles for a common multiple.
    # Tighten only the CPU timing target to 13.320ns: 91 CPU / 60 SYS
    # cycles expand exactly. Never substitute this target for CPU_HZ or TIME.
    if ((Get-SocCpuClockMode $Clock) -eq 2) { return [decimal]13.320 }
    return [decimal]1000000000 * $Clock.cpu_divisor / (Get-SocCpuPllVcoHz $Clock)
}
function Get-SocSysConstraintPeriodNs($Clock) {
    $physical=[decimal]1000000000/[decimal]$Clock.sys_hz
    # Make the CPU75 common-multiple proof hold for complete FDC literals,
    # not just the clock-summary display. This tightens SYS by only 20fs.
    if ((Get-SocCpuClockMode $Clock) -ge 2) { return [decimal]::Floor($physical*1000)/1000 }
    return $physical
}
function Assert-SocCpuClockHardware([string]$Root, $Clock) {
    $top=[IO.File]::ReadAllText((Join-Path $Root 'rtl/soc/soc_top.v'))
    $mode=Get-SocCpuClockMode $Clock
    $fdc=[IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc'))
    $cpuNet=if($mode -in @(4,5,6)){'g_dedicated_cpu.u_cpu_pll/clkout0'}elseif($mode -ne 0){'g_dedicated_cpu.u_cpu_pll/clkout3'}else{'u_video_pll/clkout3'}
    $cpuClockLine='(?m)^create_clock -name \{cpu_clk\} -period \{[0-9.]+\} \[get_nets \{'+[regex]::Escape($cpuNet)+'\}\]\s*$'
    if([regex]::Matches($fdc,$cpuClockLine).Count -ne 1){throw 'FDC CPU clock target differs from actual CPU PLL output'}
    $newTopology=$top -match 'parameter integer CPU_CLOCK_MODE'
    if ($newTopology) {
        foreach ($pattern in @(
            ('parameter integer CPU_CLOCK_MODE\s*=\s*'+$mode+'\b'),
            "parameter \[31:0\] CPU_PLL_VCO_HZ\s*=\s*(?:CPU_CLOCK_MODE == 6 \? 32'd945000000 : )?(?:CPU_CLOCK_MODE == 5 \? 32'd1147500000 : )?CPU_CLOCK_MODE == 4 \? 32'd1080000000 : CPU_CLOCK_MODE == 3 \? 32'd800000000 : CPU_CLOCK_MODE == 2 \? 32'd675000000 : CPU_CLOCK_MODE \? 32'd850500000 : 32'd891000000",
            "parameter \[31:0\] CPU_HZ\s*=\s*CPU_CLOCK_MODE (?:==|>=) 4 \? \(CPU_PLL_VCO_HZ \* 32'd2 \+ CPU_DIVISOR/2\) / CPU_DIVISOR : \(CPU_PLL_VCO_HZ \+ CPU_DIVISOR/2\) / CPU_DIVISOR",
            'if\s*\(CPU_CLOCK_MODE != 0\)\s*begin\s*:\s*g_dedicated_cpu',
            "assign cpu_clk\s*=\s*video_cpu_clk;\s*assign cpu_pll_lock\s*=\s*1'b1;",
            'wire domains_async_resetn = rst_board && video_pll_lock && cpu_pll_lock;'
        )) {
            if ([regex]::Matches($top,$pattern).Count -ne 1) { throw "CPU clock topology mismatch: $pattern" }
        }
    } elseif ($mode -ne 0 -or $top -notmatch "parameter \[31:0\] CPU_HZ\s*=\s*\(32'd891000000 \+ CPU_DIVISOR/2\) / CPU_DIVISOR") {
        throw 'Legacy CPU formula does not support the selected clock source'
    }
    $output=if($newTopology){'video_cpu_clk'}else{'cpu_clk'}
    $video=[regex]::Matches($top,'(?s)\bpll_video\s*#\s*\(\s*\.CPU_DIVISOR\s*\(\s*CPU_DIVISOR\s*\)\s*(?:,\s*\.PIXEL_DIVISOR\s*\(\s*(?:6|12)\s*\))?\s*\)\s+u_video_pll\s*\((?<ports>.*?)\)\s*;')
    if($video.Count -ne 1 -or $video[0].Groups['ports'].Value -notmatch '\.clkin1\s*\(\s*free_clk\s*\)' -or
        $video[0].Groups['ports'].Value -notmatch '\.clkout1\s*\(\s*sys_clk\s*\)' -or
        $video[0].Groups['ports'].Value -notmatch ('\.clkout3\s*\(\s*'+$output+'\s*\)')) {throw 'Video/SYS GPLL connection mismatch'}
    if (!$newTopology) { return }
    $cpu=[regex]::Matches($top,'(?s)\bpll_cpu\s*#\s*\(\s*\.CPU_DIVISOR\s*\(\s*CPU_DIVISOR\s*\)\s*,\s*\.CPU_CLOCK_MODE\s*\(\s*CPU_CLOCK_MODE\s*\)\s*\)\s+u_cpu_pll\s*\((?<ports>.*?)\)\s*;')
    foreach($mapping in @('\.clkin1\s*\(\s*CPU_CLOCK_MODE == 3 \? ref_clk : free_clk\s*\)','\.clkout0\s*\(\s*cpu_clk0\s*\)','\.clkout3\s*\(\s*cpu_clk3\s*\)','\.lock\s*\(\s*cpu_pll_lock\s*\)')) {
        if($cpu.Count -ne 1 -or [regex]::Matches($cpu[0].Groups['ports'].Value,$mapping).Count -ne 1){throw 'Dedicated CPU GPLL connection mismatch'}
    }
    if($top -notmatch 'assign cpu_clk=CPU_CLOCK_MODE (?:==|>=) 4 \? cpu_clk0 : cpu_clk3;'){throw 'Dedicated CPU output selection mismatch'}
    $pll=[IO.File]::ReadAllText((Join-Path $Root 'rtl/video/pll_cpu.v'))
    if($mode -eq 3 -and ($top -notmatch 'GTP_INBUFDS\s+u_refclk\s*\(\.I\(ref_clk_p\),\.IB\(ref_clk_n\),\.O\(ref_clk\)\)' -or $fdc -notmatch 'create_clock -name \{ref_clk\} \[get_ports \{ref_clk_p\}\] -period \{8\.0\}')){throw 'CPU80 requires the reviewed125MHz differential reference'}
    foreach($pair in @(@('CLKIN_FREQ','CPU_CLOCK_MODE == 3 \? 125\.0 : 27\.0'),@('STATIC_RATIOI','CPU_CLOCK_MODE == 3 \? 5 : 1'),@('STATIC_RATIOM','CPU_CLOCK_MODE >= 2 \? 1 : 2'),@('STATIC_RATIOF','(?:CPU_CLOCK_MODE == 6 \? 35\.0 : )?(?:CPU_CLOCK_MODE == 5 \? 42\.5 : )?CPU_CLOCK_MODE == 4 \? 40\.0 : CPU_CLOCK_MODE == 3 \? 32\.0 : CPU_CLOCK_MODE == 2 \? 25\.0 : 15\.75'),@('STATIC_RATIO0','CPU_CLOCK_MODE (?:==|>=) 4 \? CPU_DIVISOR / 2\.0 : 12\.0'),@('STATIC_DUTY0','CPU_CLOCK_MODE (?:==|>=) 4 \? CPU_DIVISOR / 2 : 12'),@('STATIC_CPHASE0','CPU_CLOCK_MODE (?:==|>=) 4 \? 1 : 0'))) {
        if([regex]::Matches($pll,'(?m)^\s*localparam\s+(?:real|integer)\s+'+$pair[0]+'\s*=\s*'+$pair[1]+'\s*;').Count -ne 1){throw "Dedicated CPU GPLL literal mismatch: $($pair[0])"}
    }
    foreach($name in @('CLKIN_FREQ','STATIC_RATIOI','STATIC_RATIOM','STATIC_RATIOF','STATIC_RATIO0','STATIC_DUTY0','STATIC_CPHASE0','STATIC_RATIO3','STATIC_DUTY3')) {
        if([regex]::Matches($pll,'\.'+$name+'\s*\(\s*'+$name+'\s*\)').Count -ne 1){throw 'Dedicated CPU GPLL primitive parameter mismatch'}
    }
    foreach($pattern in @('STATIC_RATIO3\s*=\s*CPU_DIVISOR','STATIC_DUTY3\s*=\s*CPU_DIVISOR',
        '\.CLKIN1\s*\(\s*clkin1\s*\)','\.CLKOUT3\s*\(\s*clkout3\s*\)',
        "assign clkin_sel\s*=\s*1'b0;","assign dps_en\s*=\s*1'b0;")) {
        if([regex]::Matches($pll,$pattern).Count -ne 1){throw 'Dedicated CPU GPLL output or static mode mismatch'}
    }
    foreach($pair in @(@('INTERNAL_FB','CLKOUTF'),@('EXTERNAL_FB','DISABLE'),@('SSC_MODE','DISABLE'),@('CLK_DPS3_EN','FALSE'),@('CLKOUT3_SYN_EN','FALSE'))) {
        if([regex]::Matches($pll,'(?m)^\s*localparam\s+'+$pair[0]+'\s*=\s*"'+$pair[1]+'"\s*;').Count -ne 1){throw 'Dedicated CPU GPLL feedback or dynamic mode mismatch'}
    }
}
function Assert-SocClockIntent($Clock) {
    $mode=Get-SocCpuClockMode $Clock
    $cpuVco=Get-SocCpuPllVcoHz $Clock
    if (($mode -eq 6 -and ($Clock.cpu_pll_vco_hz -ne 945000000 -or $Clock.cpu_divisor -ne 27 -or $Clock.cpu_reference_hz -ne 27000000 -or $Clock.cpu_output_divisor_eighths -ne 108)) -or
        ($mode -eq 5 -and ($Clock.cpu_pll_vco_hz -ne 1147500000 -or $Clock.cpu_divisor -ne 27 -or $Clock.cpu_reference_hz -ne 27000000 -or $Clock.cpu_output_divisor_eighths -ne 108)) -or
        ($mode -eq 4 -and ($Clock.cpu_pll_vco_hz -ne 1080000000 -or $Clock.cpu_divisor -notin @(27,36) -or $Clock.cpu_reference_hz -ne 27000000 -or $Clock.cpu_output_divisor_eighths -ne $Clock.cpu_divisor*4)) -or
        ($mode -eq 3 -and ($Clock.cpu_pll_vco_hz -ne 800000000 -or $Clock.cpu_divisor -ne 10 -or $Clock.cpu_reference_hz -ne 125000000)) -or
        ($mode -eq 2 -and ($Clock.cpu_pll_vco_hz -ne 675000000 -or $Clock.cpu_divisor -ne 9)) -or
        ($mode -eq 1 -and ($Clock.cpu_pll_vco_hz -ne 850500000 -or $Clock.cpu_divisor -ne 12)) -or
        ($mode -eq 0 -and $null -ne $Clock.cpu_pll_vco_hz -and $Clock.cpu_pll_vco_hz -ne 891000000)) {
        throw 'CPU PLL profile or VCO differs from the reviewed source'
    }
    if ($Clock.schema -ne 1 -or $Clock.integer_hz_rounding -cne 'nearest_half_up' -or
        $Clock.input_hz -ne 27000000 -or $Clock.pll_vco_hz -ne 891000000 -or
        $Clock.cpu_divisor -notin @(36,27,18,17,16,15,14,13,12,10,9) -or ($mode -ne 2 -and $Clock.cpu_divisor -eq 9) -or ($mode -ne 3 -and $Clock.cpu_divisor -eq 10) -or ($mode -notin @(4,5,6) -and $Clock.cpu_divisor -eq 27) -or ($Clock.cpu_divisor -eq 36 -and $mode -ne 4) -or
        $Clock.cpu_hz -ne [decimal]::Floor($cpuVco * $(if($mode -in @(4,5,6)){2}else{1}) / $Clock.cpu_divisor + [decimal]0.5) -or
        $Clock.sys_hz -ne 49500000 -or $Clock.timebase_hz -ne 49500000) {
        throw 'Invalid bounded CPU/SYS/TIMEBASE clock configuration (reviewed divisors 12..18)'
    }
}

function Get-SocCdcLimitNs([decimal]$CpuPeriodNs, [decimal]$SysPeriodNs) {
    # Never relax the historical 16 ns bound. Keep at least 0.8 ns below
    # the faster domain's period, rounding downward to PDS's 1 ps grid.
    $limit = [Math]::Min([decimal]16, [Math]::Min($CpuPeriodNs, $SysPeriodNs) - [decimal]0.8)
    if ($limit -le 0) { throw 'CPU/SYS periods leave no CDC timing budget' }
    return [decimal]::Floor($limit * 1000) / [decimal]1000
}

function Get-SocFdcCdcLimitNs([string]$Fdc) {
    $periods = @{}
    foreach ($name in @('cpu_clk','sys_clk')) {
        $found = [regex]::Matches($Fdc, '(?m)^create_clock -name \{' + $name + '\} -period \{([0-9.]+)\}')
        if ($found.Count -ne 1) { throw "Missing/duplicate $name FDC clock" }
        $periods[$name] = [decimal]::Parse($found[0].Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
    }
    return Get-SocCdcLimitNs $periods.cpu_clk $periods.sys_clk
}

function Assert-SocCdcBounds([string]$Fdc) {
    $limit = Get-SocFdcCdcLimitNs $Fdc
    $lines = @($Fdc -split '\r?\n' | Where-Object {
        $_ -match '^set_(?:max_delay|max_skew)\b' -and ($_ -match 'u_axi_cdc|u_irq_sync')
    })
    if ($lines.Count -ne 29 -or
        @($lines | Where-Object { $_ -match '^set_max_delay\b' }).Count -ne 19 -or
        @($lines | Where-Object { $_ -match '^set_max_skew\b' }).Count -ne 10) {
        throw 'CDC requires exactly nineteen max-delay and ten max-skew bounds'
    }
    foreach ($line in $lines) {
        $match = [regex]::Match($line, ' ([0-9.]+)\s*$')
        if (!$match.Success -or
            [decimal]::Parse($match.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) -ne $limit) {
            throw "CDC bound differs from the conservative CPU/SYS period budget $limit ns: $line"
        }
    }
    return $limit
}
# Historical records use their original name; new records carry an explicit,
# versioned, unique path in both archive manifests. Never guess the latest run.
function Get-SocCandidateEvidenceRelative([int]$Divisor, [string]$Declared) {
    if (!$Declared) { return "docs/validation/frequency-search/divisor-$Divisor.inputs.json" }
    $legacy = "docs/validation/frequency-search/divisor-$Divisor.inputs.json"
    $pattern = '^docs/validation/frequency-search/candidates/V\d+\.\d+(?:\.\d+)?/div' + $Divisor + '-\d{8}T\d{6,13}Z-[0-9a-f]{32}\.inputs\.json$'
    if ($Declared -cne $legacy -and $Declared -cnotmatch $pattern) { throw 'Invalid or mismatched clock candidate evidence path' }
    return $Declared
}
