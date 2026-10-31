# Reviewed PG2L100H GPLL search window. Hardware legality is not a timing pass.
# PDS 2022.2-SP6.4 UG041001_PLL_IP: ODIV3 is integer 1..128;
# The video/SYS PLL remains at 891 MHz. The dedicated CPU profile uses
# IDIV=1, MDIV=2, FDIV=15.75 (legal n/8 feedback), ODIV3=12.
function Get-SocCpuClockMode($Clock) {
    $source=$Clock.cpu_clock_source
    if (!$source -or $source -ceq 'video891') { return 0 }
    if ($source -ceq 'dedicated850p5') { return 1 }
    if ($source -ceq 'dedicated675') { return 2 }
    throw 'Unsupported CPU clock source'
}
function Get-SocCpuPllVcoHz($Clock) {
    if ((Get-SocCpuClockMode $Clock) -eq 2) { return [decimal]675000000 }
    if ((Get-SocCpuClockMode $Clock) -eq 1) { return [decimal]850500000 }
    return [decimal]891000000
}
function Get-SocCpuConstraintPeriodNs($Clock) {
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
    if ((Get-SocCpuClockMode $Clock) -eq 2) { return [decimal]::Floor($physical*1000)/1000 }
    return $physical
}
function Assert-SocCpuClockHardware([string]$Root, $Clock) {
    $top=[IO.File]::ReadAllText((Join-Path $Root 'rtl/soc/soc_top.v'))
    $mode=Get-SocCpuClockMode $Clock
    $fdc=[IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc'))
    $cpuNet=if($mode -ne 0){'g_dedicated_cpu.u_cpu_pll/clkout3'}else{'u_video_pll/clkout3'}
    $cpuClockLine='(?m)^create_clock -name \{cpu_clk\} -period \{[0-9.]+\} \[get_nets \{'+[regex]::Escape($cpuNet)+'\}\]\s*$'
    if([regex]::Matches($fdc,$cpuClockLine).Count -ne 1){throw 'FDC CPU clock target differs from actual CPU PLL output'}
    $newTopology=$top -match 'parameter integer CPU_CLOCK_MODE'
    if ($newTopology) {
        foreach ($pattern in @(
            ('parameter integer CPU_CLOCK_MODE\s*=\s*'+$mode+'\b'),
            "parameter \[31:0\] CPU_PLL_VCO_HZ\s*=\s*CPU_CLOCK_MODE == 2 \? 32'd675000000 : CPU_CLOCK_MODE \? 32'd850500000 : 32'd891000000",
            'parameter \[31:0\] CPU_HZ\s*=\s*\(CPU_PLL_VCO_HZ \+ CPU_DIVISOR/2\) / CPU_DIVISOR',
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
    $video=[regex]::Matches($top,'(?s)\bpll_video\s*#\s*\(\s*\.CPU_DIVISOR\s*\(\s*CPU_DIVISOR\s*\)\s*\)\s+u_video_pll\s*\((?<ports>.*?)\)\s*;')
    if($video.Count -ne 1 -or $video[0].Groups['ports'].Value -notmatch '\.clkin1\s*\(\s*free_clk\s*\)' -or
        $video[0].Groups['ports'].Value -notmatch '\.clkout1\s*\(\s*sys_clk\s*\)' -or
        $video[0].Groups['ports'].Value -notmatch ('\.clkout3\s*\(\s*'+$output+'\s*\)')) {throw 'Video/SYS GPLL connection mismatch'}
    if (!$newTopology) { return }
    $cpu=[regex]::Matches($top,'(?s)\bpll_cpu\s*#\s*\(\s*\.CPU_DIVISOR\s*\(\s*CPU_DIVISOR\s*\)\s*,\s*\.CPU_CLOCK_MODE\s*\(\s*CPU_CLOCK_MODE\s*\)\s*\)\s+u_cpu_pll\s*\((?<ports>.*?)\)\s*;')
    foreach($mapping in @('\.clkin1\s*\(\s*free_clk\s*\)','\.clkout3\s*\(\s*cpu_clk\s*\)','\.lock\s*\(\s*cpu_pll_lock\s*\)')) {
        if($cpu.Count -ne 1 -or [regex]::Matches($cpu[0].Groups['ports'].Value,$mapping).Count -ne 1){throw 'Dedicated CPU GPLL connection mismatch'}
    }
    $pll=[IO.File]::ReadAllText((Join-Path $Root 'rtl/video/pll_cpu.v'))
    foreach($pair in @(@('CLKIN_FREQ','27\.0'),@('STATIC_RATIOI','1'),@('STATIC_RATIOM','CPU_CLOCK_MODE == 2 \? 1 : 2'),@('STATIC_RATIOF','CPU_CLOCK_MODE == 2 \? 25\.0 : 15\.75'))) {
        if([regex]::Matches($pll,'(?m)^\s*localparam\s+(?:real|integer)\s+'+$pair[0]+'\s*=\s*'+$pair[1]+'\s*;').Count -ne 1){throw "Dedicated CPU GPLL literal mismatch: $($pair[0])"}
    }
    foreach($name in @('CLKIN_FREQ','STATIC_RATIOI','STATIC_RATIOM','STATIC_RATIOF','STATIC_RATIO3','STATIC_DUTY3')) {
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
    if (($mode -eq 2 -and ($Clock.cpu_pll_vco_hz -ne 675000000 -or $Clock.cpu_divisor -ne 9)) -or
        ($mode -eq 1 -and ($Clock.cpu_pll_vco_hz -ne 850500000 -or $Clock.cpu_divisor -ne 12)) -or
        ($mode -eq 0 -and $null -ne $Clock.cpu_pll_vco_hz -and $Clock.cpu_pll_vco_hz -ne 891000000)) {
        throw 'CPU PLL profile or VCO differs from the reviewed source'
    }
    if ($Clock.schema -ne 1 -or $Clock.integer_hz_rounding -cne 'nearest_half_up' -or
        $Clock.input_hz -ne 27000000 -or $Clock.pll_vco_hz -ne 891000000 -or
        $Clock.cpu_divisor -notin @(18,17,16,15,14,13,12,9) -or ($mode -ne 2 -and $Clock.cpu_divisor -eq 9) -or
        $Clock.cpu_hz -ne [decimal]::Floor($cpuVco / $Clock.cpu_divisor + [decimal]0.5) -or
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
