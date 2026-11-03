param(
    [Parameter(Mandatory=$true)][ValidateSet(36,27,24,20,18,17,16,15,14,13,12,10,9)][int]$Divisor,
    [string]$DtcPath = 'D:\LJL\WORK\msys64\usr\bin\dtc.exe',
    [string]$Root = '',
    [ValidateSet('video891','dedicated850p5','dedicated675','dedicated800','dedicated1080frac','dedicated1147p5frac','dedicated945frac','dedicated950frac','dedicated1000frac','dedicated1100frac','dedicated1200frac','dedicated975frac')][string]$CpuClockSource = '',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
if (!$Root) { $Root = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($Root)
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$clockPath = Join-Path $root 'config/clocks.json'
$clock = [IO.File]::ReadAllText($clockPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
Assert-SocClockIntent $clock
$dtcWsl = $DtcPath -ceq '/usr/bin/dtc'
if (!$dtcWsl -and !(Test-Path -LiteralPath $DtcPath -PathType Leaf)) { throw "dtc is missing: $DtcPath" }
if (!$dtcWsl) { $DtcPath = [IO.Path]::GetFullPath($DtcPath) }
function Invoke-ClockDtc([string[]]$DtcArguments) {
    if ($dtcWsl) {
        $converted = @($DtcArguments | ForEach-Object {
            if ($_ -match '^[A-Za-z]:[\\/]') { '/mnt/' + $_.Substring(0,1).ToLowerInvariant() + $_.Substring(2).Replace('\','/') } else { $_ }
        })
        $savedPreference=$ErrorActionPreference
        try {
            $ErrorActionPreference='Continue'
            & wsl.exe -d pikafish-verify -- /usr/bin/dtc @converted 2>$null
            if ($LASTEXITCODE -ne 0) { throw "WSL dtc failed: $LASTEXITCODE" }
        } finally { $ErrorActionPreference=$savedPreference }
    } else { & $DtcPath @DtcArguments }
}
$dtcHash = if ($dtcWsl) { ((& wsl.exe -d pikafish-verify -- sha256sum /usr/bin/dtc) -split '\s+')[0] } else { (Get-FileHash -LiteralPath $DtcPath -Algorithm SHA256).Hash.ToLowerInvariant() }
if ($dtcHash -notmatch '^[0-9a-f]{64}$') { throw 'Cannot bind actual dtc executable hash' }
& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $root

if(!$CpuClockSource){$CpuClockSource=if((Get-SocCpuClockMode $clock) -eq 4){'dedicated1080frac'}elseif((Get-SocCpuClockMode $clock) -eq 3){'dedicated800'}elseif((Get-SocCpuClockMode $clock) -eq 2){'dedicated675'}elseif((Get-SocCpuClockMode $clock) -eq 1){'dedicated850p5'}else{'video891'}}
$targetMode=if($CpuClockSource -ceq 'dedicated975frac'){11}elseif($CpuClockSource -ceq 'dedicated1200frac'){10}elseif($CpuClockSource -ceq 'dedicated1100frac'){9}elseif($CpuClockSource -ceq 'dedicated1000frac'){8}elseif($CpuClockSource -ceq 'dedicated950frac'){7}elseif($CpuClockSource -ceq 'dedicated945frac'){6}elseif($CpuClockSource -ceq 'dedicated1147p5frac'){5}elseif($CpuClockSource -ceq 'dedicated1080frac'){4}elseif($CpuClockSource -ceq 'dedicated800'){3}elseif($CpuClockSource -ceq 'dedicated675'){2}elseif($CpuClockSource -ceq 'dedicated850p5'){1}else{0}
$cpuVco=if($targetMode -eq 11){[decimal]975000000}elseif($targetMode -eq 10){[decimal]1200000000}elseif($targetMode -eq 9){[decimal]1100000000}elseif($targetMode -eq 8){[decimal]1000000000}elseif($targetMode -eq 7){[decimal]950000000}elseif($targetMode -eq 6){[decimal]945000000}elseif($targetMode -eq 5){[decimal]1147500000}elseif($targetMode -eq 4){[decimal]1080000000}elseif($targetMode -eq 3){[decimal]800000000}elseif($targetMode -eq 2){[decimal]675000000}elseif($targetMode -eq 1){[decimal]850500000}else{[decimal]891000000}
if(($targetMode -in @(5,6) -and $Divisor -ne 27) -or ($targetMode -eq 4 -and $Divisor -notin @(24,27,36))){throw 'CPU PLL mode4 permits encoded24/27/36 (90/80/60MHz); mode5 requires27'}
if($targetMode -eq 3 -and $Divisor -ne 10){throw 'Dedicated CPU80 profile requires divisor10'}
if($targetMode -eq 2 -and $Divisor -ne 9){throw 'Dedicated CPU75 profile requires divisor 9'}
if($targetMode -eq 1 -and $Divisor -ne 12){throw 'Dedicated CPU profile requires divisor 12'}
$factor=if($targetMode -in @(4,5,6,7,8,9,10,11)){2}else{1}
$hz = [int][decimal]::Floor($cpuVco * $factor / $Divisor + [decimal]0.5)
$physicalPeriod = [decimal]1000000000 * $Divisor / ($cpuVco * $factor)
$targetIntent=[pscustomobject]@{cpu_clock_source=$CpuClockSource;cpu_divisor=$Divisor;sys_hz=$clock.sys_hz}
$period = (Get-SocCpuConstraintPeriodNs $targetIntent).ToString('0.000000', [Globalization.CultureInfo]::InvariantCulture)
$sysPeriod = (Get-SocSysConstraintPeriodNs $targetIntent).ToString('0.000000', [Globalization.CultureInfo]::InvariantCulture)
$original = @{}
$planned = @{}
$hadBom = @{}
function Get-ClockText([string]$Relative) {
    if (!$script:planned.ContainsKey($Relative)) {
        $path = Join-Path $script:root $Relative
        $bytes = [IO.File]::ReadAllBytes($path)
        $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf
        $offset = if ($bom) { 3 } else { 0 }
        $script:original[$Relative] = $bytes
        $script:hadBom[$Relative] = $bom
        $script:planned[$Relative] = [Text.UTF8Encoding]::new($false, $true).GetString($bytes, $offset, $bytes.Length - $offset)
    }
    return $script:planned[$Relative]
}
function Set-ClockAnchor([string]$Relative, [string]$Pattern, [string]$Value) {
    $content = Get-ClockText $Relative
    $matches = [regex]::Matches($content, $Pattern)
    if ($matches.Count -ne 1 -or !$matches[0].Groups['value'].Success) {
        throw "Clock anchor must occur exactly once: $Relative / $Pattern (found $($matches.Count))"
    }
    $field = $matches[0].Groups['value']
    $script:planned[$Relative] = $content.Substring(0, $field.Index) + $Value +
        $content.Substring($field.Index + $field.Length)
}
function Get-PlannedBytes([string]$Relative) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($script:planned[$Relative])
    if ($script:hadBom[$Relative]) {
        $withBom = New-Object byte[] ($bytes.Length + 3)
        [Array]::Copy([byte[]]@(0xef,0xbb,0xbf), $withBom, 3)
        [Array]::Copy($bytes, 0, $withBom, 3, $bytes.Length)
        return ,$withBom
    }
    return ,$bytes
}
function Get-BytesSha256([byte[]]$Bytes) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($Bytes)).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

Set-ClockAnchor 'config/clocks.json' '(?m)^\s*"cpu_divisor"\s*:\s*(?<value>\d+)\s*,?\s*$' "$Divisor"
Set-ClockAnchor 'config/clocks.json' '(?m)^\s*"cpu_hz"\s*:\s*(?<value>\d+)\s*,?\s*$' "$hz"
$newClock=(Get-ClockText 'config/clocks.json')|ConvertFrom-Json
$newClock|Add-Member -NotePropertyName cpu_clock_source -NotePropertyValue $CpuClockSource -Force
$newClock|Add-Member -NotePropertyName cpu_pll_vco_hz -NotePropertyValue ([int]$cpuVco) -Force
$newClock|Add-Member -NotePropertyName cpu_reference_hz -NotePropertyValue $(if($targetMode -in @(3,7,8,9,10,11)){125000000}else{27000000}) -Force
$newClock|Add-Member -NotePropertyName cpu_output_divisor_eighths -NotePropertyValue $(if($targetMode -in @(4,5,6,7,8,9,10,11)){$Divisor*4}else{$Divisor*8}) -Force
Assert-SocClockIntent $newClock
$planned['config/clocks.json']=($newClock|ConvertTo-Json -Depth 6)+"`n"
$scope=(Get-ClockText 'config/timing_scope_baseline.json')|ConvertFrom-Json
$scope.clocks.cpu_clk.target=if($targetMode -in @(4,5,6,7,8,9,10,11)){'{ g_dedicated_cpu.u_cpu_pll/u_gpll/gpll_inst/CLKOUT0 }'}elseif($targetMode -ne 0){'{ g_dedicated_cpu.u_cpu_pll/u_gpll/gpll_inst/CLKOUT3 }'}else{'{ u_video_pll/u_gpll/gpll_inst/CLKOUT3 }'}
$planned['config/timing_scope_baseline.json']=($scope|ConvertTo-Json -Depth 12)+"`n"
foreach ($relative in @('rtl/video/pll_video.v','rtl/soc/soc_top.v')) {
    Set-ClockAnchor $relative '(?m)^\s*parameter integer CPU_DIVISOR\s*=\s*(?<value>\d+)' "$Divisor"
}
$top=Get-ClockText 'rtl/soc/soc_top.v'
if($top -match 'parameter integer CPU_CLOCK_MODE'){
    Set-ClockAnchor 'rtl/soc/soc_top.v' '(?m)^\s*parameter integer CPU_CLOCK_MODE\s*=\s*(?<value>\d+)' "$targetMode"
}elseif($targetMode -ne 0){throw 'Dedicated CPU profile requires the reviewed SoC topology'}
Set-ClockAnchor 'pds/soc.fdc' '(?m)^create_clock -name \{cpu_clk\} -period \{(?<value>[0-9.]+)\}' $period
Set-ClockAnchor 'pds/soc.fdc' '(?m)^create_clock -name \{sys_clk\} -period \{(?<value>[0-9.]+)\}' $sysPeriod
$cpuNet=if($targetMode -in @(4,5,6,7,8,9,10,11)){'g_dedicated_cpu.u_cpu_pll/clkout0'}elseif($targetMode -ne 0){'g_dedicated_cpu.u_cpu_pll/clkout3'}else{'u_video_pll/clkout3'}
Set-ClockAnchor 'pds/soc.fdc' '(?m)^create_clock -name \{cpu_clk\} -period \{[0-9.]+\} \[get_nets \{(?<value>[^}]+)\}\]' $cpuNet
$cdcLimit = Get-SocCdcLimitNs (Get-SocCpuConstraintPeriodNs $targetIntent) (Get-SocSysConstraintPeriodNs $targetIntent)
$cdcLiteral = $cdcLimit.ToString('0.0##', [Globalization.CultureInfo]::InvariantCulture)
$cdcPattern = '(?m)^(set_(?:max_delay|max_skew) [^\r\n]*(?:u_axi_cdc|u_irq_sync)[^\r\n]* )([0-9.]+)(\r?)$'
if ([regex]::Matches($planned['pds/soc.fdc'], $cdcPattern).Count -ne 29) {
    throw 'Clock generator requires all twenty-nine reviewed CDC max-delay/skew directives'
}
$planned['pds/soc.fdc'] = [regex]::Replace($planned['pds/soc.fdc'], $cdcPattern, {
    param($match) $match.Groups[1].Value + $cdcLiteral + $match.Groups[3].Value
})
$planned['pds/soc.fdc'] = $planned['pds/soc.fdc'].Replace(
    '# Setup is data-path bounded below the 891 MHz / 15 CPU period (16.835 ns).',
    '# Bounds are min(16 ns, faster CPU/SYS period minus 0.8 ns), floored to 1 ps.')
$null = Assert-SocCdcBounds $planned['pds/soc.fdc']
Set-ClockAnchor 'sw/bootloader/soc.h' '(?m)^#define CPU_CLOCK_HZ\s+(?<value>\d+)u$' "$hz"
Set-ClockAnchor 'linux/soc.dts' '(?m)^\s*clock-frequency\s*=\s*<(?<value>\d+)>;' "$hz"
$cpuRtl = [IO.File]::ReadAllText((Join-Path $root 'rtl/cpu/CoreTop.sv'))
$linuxTimeHz = [int]$clock.timebase_hz
if (!$cpuRtl.Contains('SYNTHETIC CPU source')) {
    if ($cpuRtl -notmatch "io_csrRnum == 12'hC01\s*\?\s*cycle\[31:0\]") {
        throw 'CPU TIME CSR is not mapped to CPU cycle'
    }
    $linuxTimeHz = $hz
    Set-ClockAnchor 'linux/soc.dts' '(?m)^\s*timebase-frequency\s*=\s*<(?<value>\d+)>;' "$linuxTimeHz"
}
Set-ClockAnchor 'sim/tb_cpu_integration.sv' '(?m)^\s*integer coremark_cpu_hz\s*=\s*(?<value>\d+);' "$hz"
foreach ($relative in @('scripts/coremark_fixed_bootloader.ps1',
        'scripts/run_coremark_production_sim.ps1','scripts/measure_coremark.ps1')) {
    Set-ClockAnchor $relative '(?m)^\s*\[ValidateRange\(1,\s*1000000000\)\]\[(?:int|long)\]\$CpuHz\s*=\s*(?<value>\d+)' "$hz"
}

$tempStem = Join-Path ([IO.Path]::GetTempPath()) ('soc_clock_candidate_' + [guid]::NewGuid().ToString('N'))
$tempDts = $tempStem + '.dts'
$tempDtb = $tempStem + '.dtb'
$dtbRelative = 'linux/boot/soc.dtb'
$dtbPath = Join-Path $root $dtbRelative
$originalDtb = [IO.File]::ReadAllBytes($dtbPath)
try {
    [IO.File]::WriteAllBytes($tempDts, (Get-PlannedBytes 'linux/soc.dts'))
    Invoke-ClockDtc @('-I','dts','-O','dtb','-o',$tempDtb,$tempDts)
    if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $tempDtb -PathType Leaf)) { throw 'Candidate dtc build failed' }
    $plannedDtb = [IO.File]::ReadAllBytes($tempDtb)
    $decoded = Invoke-ClockDtc @('-I','dtb','-O','dts',$tempDtb) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or
        [regex]::Matches($decoded, '(?m)^\s*clock-frequency = <0x' + $hz.ToString('x') + '>;').Count -ne 1 -or
        [regex]::Matches($decoded, '(?m)^\s*timebase-frequency = <0x' + $linuxTimeHz.ToString('x') + '>;').Count -ne 1) {
        throw 'Candidate DTB does not encode the requested CPU/TIME CSR frequencies'
    }

    $changes = @($planned.Keys | Sort-Object | Where-Object {
        (Get-BytesSha256 $original[$_]) -cne (Get-BytesSha256 (Get-PlannedBytes $_))
    })
    if ((Get-BytesSha256 $originalDtb) -cne (Get-BytesSha256 $plannedDtb)) { $changes += $dtbRelative }
    Write-Output "SOC_CLOCK_CANDIDATE_PLAN divisor=$Divisor cpu_hz=$hz sys_hz=$($clock.sys_hz) timebase_hz=$($clock.timebase_hz) cpu_period_ns=$period cdc_limit_ns=$cdcLiteral changed_files=$($changes.Count)"
    $changes | ForEach-Object { Write-Output "  $_" }
    if (!$Apply) {
        Write-Output 'SOC_CLOCK_CANDIDATE_DRY_RUN_PASS no workspace files written'
        return
    }
    if ($Divisor -eq $clock.cpu_divisor -and $targetMode -eq (Get-SocCpuClockMode $clock)) { throw 'Refusing to apply the current divisor and source; use dry-run or choose a new isolated candidate' }

    $version = [IO.File]::ReadAllText((Join-Path $root 'VERSION')).Trim()
    if ($version -notmatch '^\d+\.\d+(?:\.\d+)?$') { throw 'Clock evidence requires a valid project VERSION' }
    $createdUtc = [datetime]::UtcNow
    $candidateId = $createdUtc.ToString('yyyyMMddTHHmmssfffffffZ') + '-' + [guid]::NewGuid().ToString('N')
    $evidenceDirectory = Join-Path $root "docs/validation/frequency-search/candidates/V$version"
    $null = New-Item -ItemType Directory -Path $evidenceDirectory -Force
    $evidencePath = Join-Path $evidenceDirectory "div$Divisor-$candidateId.inputs.json"
    # Reserve this run's new name before mutating inputs. CreateNew prevents
    # overwrite even if an unexpected collision or concurrent writer exists.
    $evidenceStream = [IO.File]::Open($evidencePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($relative in $planned.Keys) {
            [IO.File]::WriteAllBytes((Join-Path $root $relative), (Get-PlannedBytes $relative))
        }
        [IO.File]::WriteAllBytes($dtbPath, $plannedDtb)
        & (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $root
        $inputs = [ordered]@{}
        foreach ($relative in @(@($planned.Keys) + @($dtbRelative) | Sort-Object -Unique)) {
            $inputs[$relative] = (Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $record = [ordered]@{
            schema = 1; kind = 'soc-cpu-clock-candidate-inputs'; cpu_divisor = $Divisor
            release = "V$version"; candidate_id = $candidateId; created_utc = $createdUtc.ToString('o')
            cpu_hz = $hz; sys_hz = [int]$clock.sys_hz; timebase_hz = [int]$clock.timebase_hz
            pll_vco_hz = [int]$clock.pll_vco_hz; fdc_cpu_period_ns = $period
            physical_cpu_period_ns = $physicalPeriod.ToString('0.000000', [Globalization.CultureInfo]::InvariantCulture)
            fdc_sys_period_ns = $sysPeriod
            cpu_clock_source = $CpuClockSource; cpu_pll_vco_hz = [int]$cpuVco
            cdc_limit_ns = $cdcLiteral; cdc_policy = 'min(16ns,min(cpu_period,sys_period)-0.8ns);floor_1ps'
            dtc_sha256 = $dtcHash
            generator_sha256 = (Get-FileHash -LiteralPath $MyInvocation.MyCommand.Path -Algorithm SHA256).Hash.ToLowerInvariant()
            inputs = $inputs; firmware_rebuild_required = $true; pds_rebuild_required = $true
        }
        $evidenceBytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 6) + "`n")
        $evidenceStream.Write($evidenceBytes, 0, $evidenceBytes.Length)
        $evidenceStream.Dispose(); $evidenceStream = $null
        Write-Output "SOC_CLOCK_CANDIDATE_APPLIED divisor=$Divisor cpu_hz=$hz inputs=$evidencePath"
    } catch {
        foreach ($relative in $original.Keys) { [IO.File]::WriteAllBytes((Join-Path $root $relative), $original[$relative]) }
        [IO.File]::WriteAllBytes($dtbPath, $originalDtb)
        if ($evidenceStream) { $evidenceStream.Dispose(); $evidenceStream = $null }
        if (Test-Path -LiteralPath $evidencePath) { Remove-Item -LiteralPath $evidencePath -Force }
        throw
    } finally {
        if ($evidenceStream) { $evidenceStream.Dispose() }
    }
} finally {
    foreach ($path in @($tempDts,$tempDtb)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force }
    }
}
