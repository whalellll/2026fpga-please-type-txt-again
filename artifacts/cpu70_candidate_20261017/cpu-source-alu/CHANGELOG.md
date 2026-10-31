# CPU source changelog

## 3.5.0 candidate — 2026-10-08 (not released)

- Move same-cycle ROB tag reuse suppression to per-tag result validity, removing
  rename allocation from result owner/data bank write controls. Targeted tests
  and equal-tick short simulation pass; new physical timing is not yet verified.
- Add short candidate profiling and schema-3 packaging with an explicit
  integrated-board receipt. Independent V3.1 scores remain historical.
- No new formal score, highest verified frequency, or release tag is asserted.

## 3.1.0 — 2026-10-04

- Moved the current Chisel CPU and `coremark_test_soc` from `cpu-v15/` to
  `cpu/`; retained original V3 evidence and the old Linux payload under
  explicit historical or legacy paths.
- Applied the approved CPU wrapper, DMA, CSR address-map, regression token,
  script and package names. Removed six configuration constants after checking
  their current consumers; preserved the external LSU ports and protocol paths.
- Re-emitted both CoreTop variants from Chisel. The synthesis RTL byte hash
  remains `b73b680b108df9ee5c3819a4c4399ef4424ab1e112e4cc329ac52e58235c0c70`;
  this is the observed result of the naming and comment cleanup.
- Added one release version source, fixed performance and validation ROM
  identities, explicit CoreMark seeds/workload/evidence class, the bounded 3+1
  RTL runner, and a portable `CPU/` source package workflow.
- Added a current-file review index and separate V3.1 validation record. The
  CPU test SoC and full integrated SoC keep distinct clocks, timing and scores.
- Completed three 10.395863-second source performance runs at 49.5 MHz,
  each 5.052514868 CoreMark/MHz, plus a separate 10.429930-second validation
  run with strict CRC checks. The fixed 2600-iteration ROM also passed the
  CPU test project's PDS Compile/ADS and post-synthesis control audit.
- Recorded the full-SoC main-tree div15 route at CPU 59.4 MHz and
  SYS/TIMEBASE 49.5 MHz: final slow/fast STA passed and a same-run bitstream
  was produced. Routed div14 at 63.642857 MHz failed final CPU slow setup
  by 2.246 ns across seven endpoints. Among tested 49.5–63.642857 MHz
  settings, 59.4 MHz is the highest complete-SoC STA passing CPU setting.
  At the user's direction, the integrated SoC release uses its 59.4 MHz,
  ten-iteration RTL pilot estimate of about 5.025 CoreMark/MHz for the
  performance seed. The official port rejected the 0.033504-second interval;
  the pilot ROM differs from the production firmware in the routed bitstream.
  No formal integrated CoreMark score or board test exists.

Release measurements, PDS controls, package hashes and hardware limitations
are recorded in [V3.1 validation](cpu/handoff/V3_1_VALIDATION.md). The final
CPU frequency conclusion belongs to the final routed `performance_soc` release build.

## 3.0.0

The V3 tag and [historical validation](cpu/handoff/VALIDATION.md) retain their
original short-run CoreMark and synthesis context. They are not V3.1 evidence.
