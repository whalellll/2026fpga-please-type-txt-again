param([Parameter(Mandatory=$true)][string]$OutputDirectory,[Parameter(Mandatory=$true)][string]$ToolchainRoot)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'compiler_capacity_helpers.ps1')
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$t=Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$elf=Join-Path $root 'artifacts/bootloader.elf'
$map=Join-Path $root 'artifacts/bootloader.map'
$o=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $o){throw 'OutputDirectory must be new.'}
New-Item -ItemType Directory -Path $o | Out-Null
$count=0
function Reject([scriptblock]$Action) {
    $rejected=$false;try { & $Action | Out-Null } catch { $rejected=$true }
    if (!$rejected) { throw 'Expected layout rejection.' };$script:count++
}
$x=Get-BootloaderCapacityLayout -Map $map -Elf $elf -Nm $t.nm
if(!$x.stack_gate_passed -or $x.static_memblk_bytes -ne 2000){throw 'Production layout failed.'};$count++
$x | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $o 'actual-layout.json')
$text=[regex]::Replace([IO.File]::ReadAllText($map),'(?m)^\s*0x[0-9a-fA-F]+\s+static_memblk(?:\s*=.*)?\s*$','')
[IO.File]::WriteAllText("$o/without-workspace.map",$text)
Reject { Get-BootloaderCapacityLayout -Map "$o/without-workspace.map" }
[IO.File]::WriteAllText("$o/legacy.map",$text+"`n $($x.static_memblk) static_memblk`n")
$y=Get-BootloaderCapacityLayout -Map "$o/legacy.map"
if($y.stack_bytes -ne $x.stack_bytes){throw 'Legacy map changed.'};$count++
Get-BootloaderCapacityLayout -Map "$o/legacy.map" -Elf $elf -Nm $t.nm | Out-Null;$count++
[IO.File]::WriteAllText("$o/duplicate.map",$text+"`n $($x.static_memblk) static_memblk`n $($x.static_memblk) static_memblk`n")
Reject { Get-BootloaderCapacityLayout -Map "$o/duplicate.map" -Elf $elf -Nm $t.nm }
[IO.File]::WriteAllText("$o/mismatch.map",$text+"`n 0x1c000004 static_memblk`n")
Reject { Get-BootloaderCapacityLayout -Map "$o/mismatch.map" -Elf $elf -Nm $t.nm }
Reject { Get-BootloaderCapacityLayout -Map $map -Elf $elf }
& $t.objcopy --redefine-sym static_memblk=not_coremark_workspace $elf "$o/missing.elf"
if($LASTEXITCODE){throw 'objcopy fixture failed.'}
Reject { Get-BootloaderCapacityLayout -Map $map -Elf "$o/missing.elf" -Nm $t.nm }
[IO.File]::WriteAllText("$o/wrong-size.S",".section .bss`n.balign 4`n.type static_memblk,@object`nstatic_memblk:`n.space 2004`n.size static_memblk,2004`n")
[IO.File]::WriteAllText("$o/fixture.ld","SECTIONS { .bss 0x1c01af50 : { *(.bss) } __bss_end = 0x1c01b750; __stack_top = 0x1c01fff0; }")
& $t.gcc -march=rv32ima -mabi=ilp32 -nostdlib '-Wl,--build-id=none' -T "$o/fixture.ld" "$o/wrong-size.S" -o "$o/wrong-size.elf"
if($LASTEXITCODE){throw 'Wrong-size fixture did not link.'}
[IO.File]::WriteAllText("$o/fixture.map","0x1c01b750 __bss_end`n0x1c01fff0 __stack_top`n")
Reject { Get-BootloaderCapacityLayout -Map "$o/fixture.map" -Elf "$o/wrong-size.elf" -Nm $t.nm }
[IO.File]::WriteAllText("$o/equality.map","0x1c000000 static_memblk`n0x1c01bff0 __bss_end`n0x1c01fff0 __stack_top`n")
$y=Get-BootloaderCapacityLayout -Map "$o/equality.map"
if($y.stack_gate_passed){throw 'Strict equality gate relaxed.'};$count++
[IO.File]::WriteAllText("$o/bounds.map","0x1c01bff0 static_memblk`n0x1c01bff0 __bss_end`n0x1c01fff0 __stack_top`n")
Reject { Get-BootloaderCapacityLayout -Map "$o/bounds.map" }
[IO.File]::WriteAllText("$o/result.json",(@{status='PASS';checks=$count;scope='Actual ELF workspace, map agreement and strict capacity counterexamples'}|ConvertTo-Json)+"`n")
"COREMARK_CAPACITY_LAYOUT_PASS checks=$count"
