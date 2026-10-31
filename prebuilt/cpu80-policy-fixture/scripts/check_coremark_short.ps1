param(
    [Parameter(Mandatory=$true)][string]$Log,
    [Parameter(Mandatory=$true)][ValidateSet('performance','validation')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$ExpectedGccVersion,
    [ValidateSet('O2','O3')][string]$CoreMarkOptimization = 'O2'
)
$ErrorActionPreference = 'Stop'
$text = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $Log)).Replace("`r", '')
function One([string]$Pattern) {
    $found = [regex]::Matches($text, $Pattern, [Text.RegularExpressions.RegexOptions]::Multiline)
    if ($found.Count -ne 1) { throw "Expected exactly one CoreMark report field: $Pattern" }
    return $found[0].Groups[1].Value
}
if ((One '^COREMARK_MODE=(\w+)$') -ne $Mode) { throw 'Wrong CoreMark seed mode' }
if ((One '^Iterations\s*:\s*(\d+)$') -ne '10') { throw 'Expected exactly ten test iterations' }
if ((One '^CoreMark Size\s*:\s*(\d+)$') -ne '666') { throw 'Expected the standard 2000-byte workload' }
if ((One '^Compiler version\s*:\s*(.+)$') -ne "riscv32-unknown-elf-gcc $ExpectedGccVersion") { throw 'Wrong compiler report' }
if ((One '^Compiler flags\s*:\s*(.+)$') -ne "-$CoreMarkOptimization -march=rv32ima_zicsr_zifencei -mabi=ilp32") { throw 'Wrong compiler flags' }
$expected = if ($Mode -eq 'performance') { @('e9f5','e714','1fd7','8e3a') } else { @('18f2','e3c1','0747','8d84') }
$labels = @('seedcrc','[0]crclist','[0]crcmatrix','[0]crcstate')
$crc = [ordered]@{}
for ($index=0; $index -lt $labels.Count; $index++) {
    $value = One ('^' + [regex]::Escape($labels[$index]) + '\s*:\s*0x([0-9a-f]{4})$')
    if ($value -ne $expected[$index]) { throw "CoreMark CRC mismatch: $($labels[$index])" }
    $crc[$labels[$index]] = $value
}
$crc['[0]crcfinal'] = One '^\[0\]crcfinal\s*:\s*0x([0-9a-f]{4})$'
$finalExpected = if ($Mode -eq 'performance') { 'fcaf' } else { 'c64e' }
if ($crc['[0]crcfinal'] -ne $finalExpected) { throw 'Wrong fixed-ten final CRC' }
$ticks = [uint64](One '^PORT_TICKS64\s*:\s*(\d+)$')
$officialTicks = [uint64](One '^Total ticks\s*:\s*(\d+)$')
if (!$ticks -or $ticks -ge 495000000 -or $officialTicks -ne ($ticks -band 0xffffffffL)) { throw 'Invalid short-run timer report' }
$seconds = [double]::Parse((One '^Total time \(secs\):\s*([0-9.]+)$'), [Globalization.CultureInfo]::InvariantCulture)
if ([Math]::Abs($seconds - $ticks / 49500000.0) -gt 0.000001) { throw 'Printed elapsed time disagrees with actual CLINT ticks' }
$cycles = [uint64](One '^CPU_COREMARK_SHORT_EXECUTED cycles=(\d+) clint_ticks=\d+ timer_stimulus_scale=1$')
$clint = [uint64](One '^CPU_COREMARK_SHORT_EXECUTED cycles=\d+ clint_ticks=(\d+) timer_stimulus_scale=1$')
if ($cycles -ne $clint -or $ticks -ge $cycles -or $cycles -ge 20000000) { throw 'Wrong real CLINT/cycle relationship' }
[void](One '^(ERROR! Must execute for at least 10 secs for a valid result!)$')
[void](One '^(Errors detected)$')
[void](One '^(COREMARK_FAIL)$')
[void](One '^(COREMARK_DONE)$')
foreach ($line in ($text -split "`n")) {
    if (($line -match 'ERROR!|Errors detected|Cannot validate|Correct operation validated|COREMARK_PASS|CoreMark 1\.0|FATAL|%Error') -and
        $line -ne 'ERROR! Must execute for at least 10 secs for a valid result!' -and $line -ne 'Errors detected') {
        throw "Unexpected failure or false score claim: $line"
    }
}
[pscustomobject][ordered]@{
    status = 'PASS'
    scope = 'Isolated ten-iteration workload on production CPU/AXI/BRAM/CLINT/port; not full bootloader console or a valid CoreMark score'
    seed_mode = $Mode
    coremark_optimization = "-$CoreMarkOptimization"
    iterations = 10
    clint_hz = 49500000
    measured_ticks = $ticks
    total_cpu_cycles = $cycles
    timer_stimulus_scale = 1
    clock_interpretation = 'HDL edges are abstract CPU cycles; port seconds use candidate 49.5 MHz. No physical frequency or board timing is validated.'
    crc = $crc
    production_port_rejected_short_run = $true
}
