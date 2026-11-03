> Historical state below. Fresh routed STA/physical/bitstream now pass; board remains pending. See [current sbit and evidence](CPU125_CM60_Sbit_20261102.md).

# CPU125 small CoreMark optimization, 2026-11-02

The selected candidate exceeds 6.0 CoreMark/MHz in both 100-iteration RTL
diagnostics with the existing CPU hardware. It changes only the uniform
compiler recipe and the boot ROM contents. It is an unaccepted local candidate.

| Mode | Original CPU125 diagnostic | Complete rebuilt candidate | Change |
|---|---:|---:|---:|
| Performance seeds | 5.900960426 | 6.031419124 | +2.211% |
| Validation seeds | 5.890211807 | 6.011920910 | +2.066% |

The complete image rebuild compiles all 16 boot objects and all six CoreMark
objects from source. Both runs use real independent CPU125 MHz/SYS49.5 MHz
waveforms and unscaled CLINT ticks. Their durations are 0.132639/0.133069 target
seconds; neither is a formal >=10-second board score. An independent host C
oracle using hash-pinned official algorithms checks all four original/candidate
CRC results. Source hashes, model identity, inputs and raw output are preserved
under `docs/validation/cpu125-cm60-small-20261102/` and the workspace run.

Selected profile: `cm60-unroll2-lto-branch1`, GCC16.2.0, uniform
`-O2 -fno-if-conversion -fno-if-conversion2 -funroll-loops
--param=max-unroll-times=2 -flto -mbranch-cost=1`, with unchanged
`-march=rv32ima_zicsr_zifencei_zbc -mabi=ilp32`. No PGO, source algorithm,
seed, 2000-byte workspace, or production automatic-calibration change.

The CPU remains `b1164e42737a081cc640a2113c76a53d0c91a97a`, generated RTL
SHA256 `97abbc7927c1736f0d0241525b6ecafc2654f21e89f73019846d0da156ccef31`.
ALU4/MEM2, two-way 8KiB I/D caches, all timing pipeline/fanout boundaries,
official Pikafish gather/dense/cache/FC1, image and voice hardware remain
unchanged. No instructions were added. The larger ALU8/MEM4/SB4/XTheadBb
6.6 experiment is not merged; its measured +3416 LUT/+1298 FF is unnecessary
for this target. Its original evidence remains intact.

Fresh native synthesis/map subsequently confirms exactly the same resources:
45,787 LUT,34,226 FF,1,946 LUTRAM,126.5 DRM36K-equivalent and76 APM. Every
resource delta is zero. All decrypted packed primitive signal/configuration
records match except4096 boot INIT values; all1,048,576 boot data bits match
the rebuilt firmware.193 native module bodies also match after narrowly
normalizing absolute FDC comment paths and PDS vendor re-encryption metadata.
Opaque vendor bodies are qualified through the full decrypted packed inventory,
not by asserting their changing cipher text is equal.

All five production firmware builds and their source/ISA bindings pass.
The linked boot image leaves 18,008 bytes of stack, 1,624 above the unchanged
16KiB minimum, within the unchanged 128KiB BRAM. LTO may omit the local
workspace from the linker map; the capacity checker now reads its actual
ELF symbol, enforces exactly 2000 BSS bytes, and cross-checks map boundaries.
Ten compiler-profile and eleven capacity positive/negative cases pass.
CPU source/configuration synchronization and exact125 clock policy pass.

The parent SoC is `6a355cb344104b597e7cae0cab612412bccf04f1`, whose own frozen
native run passed all-corner CPU125 STA (slow setup +0.139ns, worst nonempty
summary +0.035ns). This applies to that parent artifact. The changed boot ROM
requires a new native artifact and its own final timing binding; no parent
bitstream is relabeled as this compiler candidate. Actual board CoreMark3+1,
official models/concurrency and final delivery remain pending. No UART ports
are currently enumerated. No board, SD, Flash, remote push or main promotion
has been performed for this candidate.

Work: `G:/fpga/build/cpu125-coremark60-20261102-01`.
Branch: `candidate/cpu125-coremark60-20261102-01` in performance_soc.
The independent CPU worktree is unchanged at the paired parent commit.
Resume from `status.json`; inspect actual owner/command/start before starting
native tools. Keep all new source/build/tmp/evidence within `G:/fpga`.

Rebuild production firmware with `scripts/build_bootloader_wsl.ps1
-ToolchainRoot G:/fpga/workspace/tools/riscv32-gcc16` and the four companion
firmware scripts. Synchronization that explicitly selects this recipe uses
`scripts/sync_cpu.ps1 -SourceRepo <pairedCPU> -AllowSupervisorCandidate
-AllowZbcCandidate -CoremarkCompilerProfile cm60-unroll2-lto-branch1`.
Check with `scripts/sync_cpu.ps1 -Check -SourceRepo <pairedCPU>`.
