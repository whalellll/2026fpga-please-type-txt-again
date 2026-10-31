# SoC v2 (V6.5 platform + NNUE chess acceleration): current release and reproducibility rules

## V2.1 current release scope

The V2.1 snapshot uses V3.5 RV32IMA with S/U/Sv32 at 59.4 MHz, Linux,
OpenSBI and the official Pikafish PFF1 runtime with Stage A/B hardware calls.
The v2 M-mode-only platform description below is historical and must not be
used to describe V2.1. Current hashes, STA, board scope and limitations are
in the first section of README.md and the V2.1 validation records.

This branch integrates the V6.5 platform line (linux: dual-clock CDC, CPU V3.5
import e698e3bb at 63.642857 MHz, CoreMark board evidence) with the
feature/nnue-gather-10ms line (dense MAC engine with Stage B LUT
optimizations, PFF1 Stage A gather sub-device at 0x1fe10100, conv frontend,
bare-metal Xiangqi chess stack, Pikafish Linux sources kept as archives).
The CPU is the e91c CoreTop V3.5 profile: RV32IMA Zicsr/Zifencei, M-mode
only. C and supervisor mode are not enabled, so the Linux/Pikafish boot flow
from the NNUE line cannot run on this CPU; those sources are retained as
historical/rebuildable inputs, not as supported v2 functionality.

## v2 integration state

- SoC hardware: rtl/soc/soc_top.v instantiates mac_accel_ddr_kernel_top with
  ENABLE_PFF1_GATHER(1) on the SYS clock domain; the MAC window is
  0x1fe10000..0x1fe1_01ff (dense DMA 0x00, conv decode 0x40 - gated out by
  ENABLE_CONV=0 after attempt-1 routing divergence, sources retained,
  sparse eval 0x80, PFF1 gather 0x100). rtl/vendor VexRiscv and cpu_v2_* wrappers are removed;
  the CPU is rtl/cpu/CoreTop.sv bound by rtl/cpu/source.json to CPU commit
  e698e3bb78947fd4f7a0b5095e1cdc85a81e4502 (V3.5 implementation; the CPU
  repository's main has merged the V3.5 release tag locally).
- Chess stack on this platform is bare-metal: bootloader `xqboot` loads
  xiangqi.bin + xqmodel.bin from MicroSD (FAT32, read-only) and jumps to
  0x01000000; `loadx` + `boot <entry>` is the UART XMODEM alternative.
  The GUI search evaluates the H128 sparse NNUE through the FPGA MAC engine.
  sw/pikafish_ft_stage_a and sw/pikafish_mlp_stage_b are bare-metal Stage A /
  Stage B acceptance programs against the same MMIO.
- The NNUE 10 ms goal (single complete Pikafish NNUE evaluation average
  <=10 ms, measured by the Linux rootfs command run-nnue10ms-board) is
  NOT met and NOT measurable on this M-mode platform: the defined benchmark
  requires S-mode Linux. Historical NNUE-branch measurements (61.5-66.5 ms
  warm/cold, 2026-10-09, VexRiscv 49.5 MHz) remain historical records in
  docs/NNUE_10ms_Optimization.md and docs/Pikafish_Bottleneck_20261009.md.
  Never present those numbers as v2 measurements. The v2 build itself
  passed the full PDS gates (attempt 2: STA "All Constraints Met", see
  docs/validation/v2-merge-20261011/README.md) and passed the end-to-end
  board acceptance on 2026-10-11 (FPGA sparse-NNUE evaluation, 8/8
  legality-verified engine moves, Stage A/B board programs green); the
  annotated tag v2 exists on the merge commit. Platform note kept in that
  README: sub-word uncached stores through 0x9bxxxxxx stall the CPU - MAC
  staging must stay word-store-only.

## Current source and build rules; historical results retain their identity

- Read VERSION, README, docs/BUILD.md, docs/ARCHITECTURE.md and docs/Validation.md.
- CPU V3.5 comes from the separate src repository. Run scripts/sync_cpu.ps1
  to import cpu/generated/core/CoreTop.sv, emit-config.json and initialization
  files into rtl/cpu; source.json records the source version, generator
  inputs, commit identity and file hashes. The integrated rtl/cpu_top.v
  wrapper owns CPU/SYS AXI CDC and CLINT routing. Re-run the source check
  before freezing a SoC build snapshot. Do not rewrite source.json to chase
  CPU documentation commits; e698e3bb is the frozen V3.5 implementation.
- Current hardware and rebuilt firmware use RV32IMA with Zicsr/Zifencei;
  -march=rv32ima_zicsr_zifencei -mabi=ilp32, explicit RV32/ILP32-compatible
  libgcc. CoreMark uses -O2. C and supervisor mode are not enabled in this CPU.
- Contest firmware uses GCC 16.2.0 riscv32-unknown-elf. CoreMark and camera,
  CRC, PNG and FAT hot paths use -O2; other bootloader objects use -Os.
  Build helpers verify target/version, ELF32, soft-float, no C and the actual
  libgcc identity. Keep the 16 KiB stack and ROM capacity gates.
- config/clocks.json is the clock-intent source: CPU domain CoreTop/mcycle,
  SYS domain CLINT/bus/DDR/peripherals, and fixed 49.5 MHz SYS/TIMEBASE.
  scripts/set_clock_candidate.ps1 derives candidate RTL/PLL/FDC/software/test
  literals and DTB from this config; it is dry-run unless -Apply is explicit.
  scripts/check_clock_config.ps1 checks RTL/PLL/FDC/software/DTS literals.
  The CPU clock register is SYS window +0x14 and TIMEBASE is +0x18.
- V6.5 board acceptance: run838e at 63.642857 MHz, final three-performance
  mean 5.262385177991809 CoreMark/MHz (+3.79154449%); run75f8 at 59.4 MHz is
  the separately measured control. Source of truth:
  docs/validation/v6_5-board-results-20261009/README.md and
  docs/validation/v6_5-board-release-20261009.json. Those results were
  measured on the pre-merge V6.5 bitstream; the v2 merged bitstream requires
  its own board evidence and must not inherit V6.5 acceptance by inference.
- Inspect branch, status and recent commits first; preserve unrelated changes.
  Never push without authorization.
- rtl/, sw/, ip/, config/clocks.json, pds/soc.tcl,
  pds/soc_post_synth.tcl, pds/soc.fdc, pds/audit_cpu_sys_cdc_ads.py,
  pds/ddr3_test.rcf, and the published firmware ELF/BIN/build JSON sets are
  build inputs. Keep pds/soc_gui.pds as the portable GUI source project. Run
  scripts/prepare_pds_project.ps1 before opening it; keep its paths relative.
  The normal build first audits an ADS-only project, then routes a
  post-synthesis project importing the same ADF; never begin PnR before
  resource/CPU/CDC gates. Native stage histories and hashes are published in
  build evidence. Never let GUI and scripted builds share a project.
- artifacts/ retains rebuilt binaries, ROM initialization, timing/build
  evidence and hashes after scripts/clean_generated.ps1. Bitstream names are
  only soc_top.sbit/bin. Never treat pre-merge hashes as v2 evidence.
- scripts/project_files.ps1 is the shared source/delivery inventory.
- Linux baseline binaries and the opaque Xiangqi service are fixed inputs:
  read prebuilt/README.md. Do not claim complete kernel source
  reproducibility. Linux boot-file name is soc.dtb; the pikafish.pff/.atk
  payloads, xiangqi.bin and xqmodel.bin in linux/boot are NNUE-line inputs.
- SYS_ID=0x53563300, CAPS=0x1f and the flash image/DT compatible ABI remain
  unchanged. Historical payloads retain their source identity and do not
  establish current CPU Linux support.

## Command scope

Use the current README and docs/BUILD.md entry points. Every full PnR start
uses the shared campaign budget and an explicit purpose. V6.5 formal delivery
requires its historical BoardRelease contract. For V2.1 and later work, CoreMark
performance and correctness acceptance uses real board runs only. Do not launch
RTL CoreMark simulations for release evidence. V2.1 formal delivery requires
an explicit BoardRelease manifest binding the exact bitstream, firmware, final
STA and 3 performance plus 1 validation board UART runs of at least 10 seconds
each. Functional RTL and software regressions remain required.
Incomplete builds require candidate naming. The v2 merge resets the PnR budget context:
the V6.5 campaign ledger (docs/validation/v6_5-development-20261008/) is a
closed historical record; do not reuse its remaining starts for v2 builds.

```powershell
.\scripts\run_all_tests.ps1
.\scripts\build_fpga.ps1 -PdsTimeoutSeconds 14400
.\scripts\build_xiangqi_sd.ps1        # bare-metal chess GUI+model build
.\scripts\prepare_sd_card.ps1 -Content Xiangqi <drive>   # only with explicit SD-write authorization
.\scripts\program_cram.ps1 -Program -SbitPath <...>
```

PDS target: PG2L100H-6-FBG676 / 2022.2-SP6.4. Explain duration and stopping
method before long runs. Avoid indefinite polling and persistent verbose logs.
Retain compact evidence, not debug history.

## Hardware, camera and board invariants

- Current authorization and fresh scan of exactly one PG2L100H ID0x00602899
  are required for JTAG programming. Normal tests load .sbit to volatile CRAM.
  program_cram.ps1 checks current CPU/ROM, snapshot, STA and output hashes for
  every in-repository image; its external-image option cannot bypass this check.
  Configuration/SPI Flash writes require separate explicit authorization and
  exact device/partition checks; this release task forbids all Flash writes.
- Camera is bootloader-only CMOS2, 1280x720 RGB565 little endian, top row first.
  Preserve HDMI timings, Esc DDR burst drain and terminal restoration.
- FB0/FB1 continue receiving live frames. Hold the completed displayed bank
  and matching frame number, drain writes, copy via uncached DDR to 0x9b600000,
  then release preview before UDP transfer or SD encoding.
- One transfer at a time, explicit busy Space, bounded failure/Esc, retry after
  failure. UDP success requires receiver PNG+JSON commit; SD success requires
  verified PNG+JSON data and completed FAT commit.
- camera_sd uses the same immutable CMOS2 snapshot. Its HDMI HUD never writes
  framebuffer/snapshot pixels. Only explicit camera_sd writes SDHC/FAT32.
- Share the Linux boot card; never format/overwrite boot files. Verify PNG+JSON
  and FAT metadata before success. No arbitrary power-loss guarantee; dirty FAT
  needs PC repair. Recovery must verify the same card CID before further writes.
- Never commit/package camera image captures, image metadata or .part files.
- Automated UART diagnostics do not replace user CH9350L Space and multi-image
  visual acceptance. Separate simulation, PDS and board evidence.
- Never infer new bitstream acceptance from older SD/audio/Linux board tests.

## RTL and docs

- Serialize repository/doc/evidence writes with program_cram's pre/post audits.
  Preserve failed board owners and every valid score. Use the recorded Python
  3.14.4 release interpreter explicitly: Python 3.9.7 rejects the seven-digit
  ISO fractional timestamps in these board receipts.
- No new Verilog/SystemVerilog function unless explicitly authorized. (The
  merged MacAccelCore.v retains the NNUE line's tested select_lane48 function;
  it is inherited branch content, not a new authoring in v2.)
- PDS-sensitive selectors use constant-indexed explicit logic. Compile-time
  generate/reset loops are allowed; each elaborated loop stays below 2000
  iterations. Preserve widths, cycle behavior and synthesizability.
- Control changes require regression and ADS netlist retention checks.
  build_cpu_ads_gate.ps1 also runs audit_icache_pad_ads.py and
  audit_uart_tx_pad_ads.py on the integrated ADS netlist before PnR. ADS
  structural proof alone does not establish physical retention or routed hold
  margin. Preserve the ICache PNR review limitation in
  docs/validation/b73-final-physical-review/.
- GUI and Tcl share the 140-DRM ADS budget in pds/soc.fdc. The merged design
  adds the conv frontend, Stage A gather and weight double buffer to the MAC
  subsystem; the ADS resource gate is the arbiter. A budget is not a measured
  resource count; changes to storage mapping must preserve capacity, ports and
  cycle behavior.
- GUI and Tcl must load pds/ddr3_test.rcf. Keep all final STA gates.
- Commands: docs/console调试命令.md; hardware: docs/SUPPORTED_HARDWARE.md;
  evidence/gaps: docs/Validation.md; NNUE goal/limits:
  docs/NNUE_10ms_Optimization.md. Keep historical tutorials out of current docs.
- Existing camera/FMC Bank_L6 uses 3.3V/J20. The camera manual's 2.5V conflict
  remains an unresolved electrical reliability question.

## Portable project skills (from the NNUE line)

The reusable engineering skills are in `skills/` (see skills/README.md).
They document workflows; they do not authorize Flash writes or make unchecked
hardware TODO items pass. Historical YOLOv5n TODO checklists under docs/
are archives of the NNUE line; their workflows (write tests first, focused
sim, SoC regression, board test via volatile CRAM, then docs and commit)
remain good practice for v2 items.

Never erase or write SPI/configuration Flash without fresh, explicit user
confirmation and an exact device/partition check. Normal FPGA testing uses
JTAG to volatile CRAM only. Keep README/docs and final evidence aligned with
the tested sources. Building or documenting the project does not authorize
JTAG programming or any Flash erase/write.
