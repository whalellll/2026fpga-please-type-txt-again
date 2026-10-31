param([string]$ToolchainBin = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$cpuOriginalPath = $env:PATH
try {
$toolchain = Get-CpuToolchain -ToolchainBin $ToolchainBin
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$directory = Join-Path $tempBase ('cpu_isa_gate_' + [guid]::NewGuid().ToString('N'))
if (![IO.Path]::GetFullPath($directory).StartsWith($tempBase + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unsafe ISA test directory.'
}
New-Item -ItemType Directory -Path $directory | Out-Null
try {
    $linker = Join-Path $directory 'link.ld'
    [IO.File]::WriteAllText($linker, @'
OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
 . = 0x01000000;
 .text : { __cpu_code_start = .; *(.text*) __cpu_code_end = .; }
 .rodata : { *(.rodata*) }
}
'@)
    foreach ($case in @(
        @{Name='data_is_not_code'; Code='addi a0,zero,1'; Reject=$false},
        @{Name='vlenb_in_code'; Code='.word 0xc2202573'; Reject=$true},
        @{Name='unknown_opcode'; Code='.word 0xffffffff'; Reject=$true}
    )) {
        $source = Join-Path $directory ($case.Name + '.S')
        $elf = Join-Path $directory ($case.Name + '.elf')
        $program = ".section .text`n.globl _start`n_start:`n" + $case.Code +
            "`njalr zero,0(ra)`n.section .rodata`n.word 0xc2202573`n.word 0x00010001`n"
        [IO.File]::WriteAllText($source, $program)
        & $toolchain.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -nostdlib -nostartfiles `
            '-Wl,--build-id=none' -T $linker $source -o $elf
        if ($LASTEXITCODE) { throw "ISA guard fixture compile failed: $($case.Name)" }
        # Bad CSR/opcode words deliberately retain valid IMA ELF attributes.
        $null = Assert-CpuElf -Readelf $toolchain.readelf -Path $elf
        $rejected = $false
        try { $null = Assert-CpuCode -Toolchain $toolchain -Elf $elf }
        catch {
            if ($_.Exception.Message -notmatch 'instruction contract|vlenb') { throw }
            $rejected = $true
        }
        if ($rejected -ne $case.Reject) { throw "ISA gate accepted/rejected the wrong fixture: $($case.Name)" }
    }
    Write-Output 'CPU_LINKED_ISA_GATE_PASS data_excluded=1 vlenb_rejected=1 unknown_opcode_rejected=1'
} finally {
    $resolved = (Get-Item -LiteralPath $directory -Force).FullName
    if (!$resolved.StartsWith($tempBase + '\cpu_isa_gate_', [StringComparison]::OrdinalIgnoreCase) -or
        ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing unsafe ISA test cleanup.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
} finally {
    $env:PATH = $cpuOriginalPath
}
