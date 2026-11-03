param([string]$Output,[string]$Root)
$ErrorActionPreference='Stop'
$env:TEMP=Join-Path (Split-Path -Parent $Output) '../tmp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP
. (Join-Path $Root 'scripts/riscv_toolchain.ps1')
$t=Get-CpuToolchain -ToolchainRoot 'G:/fpga/workspace/tools/riscv32-gcc16'
& $t.gcc "-march=$CpuMarch" "-mabi=$CpuAbi" -O2 -ffreestanding -fno-builtin -fno-common -ffunction-sections -fdata-sections -mno-relax -msmall-data-limit=0 -nostdlib -nostartfiles '-Wl,--gc-sections' '-Wl,--build-id=none' -T (Join-Path $Output 'link.ld') (Join-Path $Output 'start.S') (Join-Path $Output 'selftest.c') -o (Join-Path $Output 'selftest.elf')
if($LASTEXITCODE){throw 'Zbc board selftest compile failed'}
& $t.objcopy -O binary (Join-Path $Output 'selftest.elf') (Join-Path $Output 'selftest.bin')
if($LASTEXITCODE){throw 'Zbc board selftest objcopy failed'}
Write-CpuFirmwareEvidence -Toolchain $t -Elf (Join-Path $Output 'selftest.elf') -Binary (Join-Path $Output 'selftest.bin') -Optimization '-O2; explicit general Zbc instruction vectors; RAM-only test'
Write-Output 'ZBC_BOARD_SELFTEST_COMPILED_NOT_EXECUTED'
