$ErrorActionPreference = 'Stop'
$temporary = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('cpu-measure-test-' + [guid]::NewGuid().ToString('N'))))
$utf8 = [Text.UTF8Encoding]::new($false)
New-Item -ItemType Directory -Path $temporary | Out-Null
function New-Run([string]$Mode, [decimal]$Ticks = 495000000, [long]$CpuHz = 49500000) {
    $seed = if ($Mode -eq 'performance') { 'e9f5'; 'e714'; '1fd7'; '8e3a' } else { '18f2'; 'e3c1'; '0747'; '8d84' }
    return @"
CPU_HZ=$CpuHz
SYS_HZ=49500000
TIMEBASE_HZ=49500000
COREMARK_MODE=$Mode
CoreMark Size    : 666
Total ticks      : $($Ticks % 4294967296)
Total time (secs): $([double]($Ticks / 49500000))
Iterations       : 2000
Compiler version : riscv32-unknown-elf-gcc 14.2.0
Compiler flags   : -O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32
Memory location  : boot BRAM (static)
seedcrc          : 0x$($seed[0])
[0]crclist       : 0x$($seed[1])
[0]crcmatrix     : 0x$($seed[2])
[0]crcstate      : 0x$($seed[3])
[0]crcfinal      : 0x1234
Correct operation validated. See readme.txt for run and reporting rules.
PORT_TICKS64 : $Ticks
COREMARK_PASS
COREMARK_DONE

"@
}
function Check-Record([string]$Name, [string]$Record, [bool]$Pass, [string]$Reason = '', [long]$CpuHz = 49500000) {
    $inputPath = Join-Path $temporary ($Name + '.txt')
    $output = Join-Path $temporary $Name
    [IO.File]::WriteAllText($inputPath, $Record, $utf8)
    $failure = ''
    try {
        & (Join-Path $PSScriptRoot 'measure_coremark.ps1') -InputLog $inputPath `
            -BitstreamPath $script:artifact -FirmwarePath $script:artifact -OutputDirectory $output `
            -CompilerVersion '14.2.0' -CpuHz $CpuHz | Out-Null
    } catch { $failure = $_.Exception.Message }
    $result = Get-Content -LiteralPath (Join-Path $output 'result.json') -Raw | ConvertFrom-Json
    if ($Pass) {
        if ($failure -or $result.status -ne 'OFFLINE_VALID' -or $result.board_acceptance -or
            $result.runs.Count -ne 4 -or $result.runs[3].mode -ne 'validation') {
            throw "Valid offline fixture rejected or called board acceptance: $Name ($failure)"
        }
        $expectedScore = 2000.0 * 49500000.0 * 1000000.0 / (495000000.0 * $CpuHz)
        if ($Name -eq 'independent_cpu_clock' -and [math]::Abs($result.runs[0].coremark_per_mhz - $expectedScore) -gt 0.000001) {
            throw 'Parser used CPU_HZ as the CLINT timebase'
        }
    } elseif (!$failure -or $result.status -ne 'FAIL' -or $failure -notmatch $Reason) {
        throw "Invalid fixture accepted or rejected for the wrong reason: $Name ($failure)"
    }
}
try {
    $script:artifact = Join-Path $temporary 'synthetic-artifact.bin'
    [IO.File]::WriteAllBytes($script:artifact, [byte[]]@(1, 2, 3, 4))
    $performance = New-Run 'performance'
    $validation = New-Run 'validation'
    $valid = $performance + $performance + $performance + $validation
    Check-Record 'valid' $valid $true
    $unequal = (New-Run 'performance' 495000000) + (New-Run 'performance' 544500000) + (New-Run 'performance' 594000000) + $validation
    Check-Record 'unequal_ticks' $unequal $true
    $unequalResult = Get-Content -LiteralPath (Join-Path $temporary 'unequal_ticks/result.json') -Raw | ConvertFrom-Json
    $expectedMean = (2000.0 / 10 + 2000.0 / 11 + 2000.0 / 12) / 3
    if ([math]::Abs($unequalResult.summary.mean_coremark - $expectedMean) -gt 0.0000001 -or
        [math]::Abs($unequalResult.summary.mean_coremark_per_mhz - $expectedMean / 49.5) -gt 0.0000001) {
        throw 'Summary must average every performance score and exclude validation'
    }
    $faster = (New-Run 'performance' 495000000 55687500) * 3 + (New-Run 'validation' 495000000 55687500)
    Check-Record 'independent_cpu_clock' $faster $true '' 55687500
    Check-Record 'wrong_timebase' ($valid.Replace('TIMEBASE_HZ=49500000','TIMEBASE_HZ=55687500')) $false 'TIMEBASE frequency'
    Check-Record 'timer64' ((New-Run 'performance' 4799967296) * 3 + (New-Run 'validation' 4799967296)) $true
    Check-Record 'short' ((New-Run 'performance' 494999999) + $performance * 2 + $validation) $false 'shorter than 10'
    Check-Record 'missing_validation' ($performance * 3) $false 'three performance'
    Check-Record 'wrong_mode' ($performance * 4) $false 'Expected seed mode validation'
    Check-Record 'wrong_validation_crc' ($valid.Replace('0x0747', '0x1fd7')) $false 'CRC mismatch'
    Check-Record 'compiler' ($valid.Replace('gcc 14.2.0', 'gcc 13.2.0')) $false 'Unexpected compiler'
    Check-Record 'flags' ($valid.Replace('-march=rv32ima_', '-march=rv32imac_')) $false 'Missing compiler flag'
    Check-Record 'timer_disagreement' ($valid.Replace('Total ticks      : 495000000', 'Total ticks      : 495000001')) $false 'ticks disagree'
    Check-Record 'duplicate_timer' ($valid.Replace('PORT_TICKS64 : 495000000', "PORT_TICKS64 : 495000000`nPORT_TICKS64 : 495000000")) $false 'exactly one 64-bit'
    Check-Record 'main_zero_is_not_success' ($valid.Replace('Correct operation validated. See readme.txt for run and reporting rules.', '')) $false 'success marker'
    Check-Record 'failure' ($valid.Replace('COREMARK_PASS', 'COREMARK_FAIL')) $false 'failure marker'
    Write-Output 'COREMARK_MEASUREMENT_PARSER_PASS valid=4 rejected=11 board_acceptance=false'
} finally {
    $prefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\cpu-measure-test-'
    if (!$temporary.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
        @(Get-ChildItem -LiteralPath $temporary -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Refusing unsafe test cleanup.'
    }
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
