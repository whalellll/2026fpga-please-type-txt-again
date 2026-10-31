# CPU V3.5 development (candidate until acceptance)

- The 2026-10-08 user task supersedes historical V3.1 release workflow below.
  Use current short RTL CoreMark only; formal V3.5 performance is measured on
  performance_soc hardware (three performance plus one validation, each >=10s).
  No new independent CPU-platform formal score is assumed. Historical V3.1
  scores and evidence retain their platform/version identity.
- Integrated release requires CPU >59.4 MHz, final slow/fast routed STA,
  DRM <=140, complete RTL regression, new-CPU 59.4 MHz board control and final
  board mean >=5.120849733668798 CoreMark/MHz. Budget: 24h from
  2026-10-08T20:55:41+08:00 or six full PnR starts including control/final.
  Only the root integration workflow starts PDS PnR and records its ledger.
- Board CRAM loading and console tests are authorized after fresh identity
  checks; Flash and SD writes are forbidden. Linux boot and full peripheral
  acceptance are not added goals. Formal V3.5/v6.5 tags require every gate.
- Work on the isolated cpu-v3.5-development branch; preserve main and old tags.

## Existing source-platform guidance (V3.1 results are historical)

- This repository owns the CPU Chisel source, generated RTL and
  `cpu/coremark_test_soc` performance test platform. `performance_soc`
  is a separate integration repository; never treat the two SoCs as identical.
- Start with README.md, cpu/handoff/NEW_COMPUTER_GUIDE.md and
  cpu/handoff/V3_1_VALIDATION.md. Work from main; the original V15 branch and
  cpu/handoff/VALIDATION.md are historical context.
- CPU V3.1 and current firmware use RV32IMA, with Zicsr and Zifencei explicitly
  recorded in compiler flags. C was removed after controlled IMA/IMAC comparison;
  do not reintroduce it as an undocumented default. Record flags and hashes.
- The selected contest build uses GCC 16.2.0/O2 with actual target riscv32-unknown-elf.
  Verify -dumpmachine and -dumpfullversion; a renamed compiler is insufficient.
  Preserve GCC13.2/15.3 results as historical controls, not current release proof.
- CPU edits belong in `cpu/src/main/scala`; regenerate synthesis and simulation
  RTL and their emit-config.json files together; verify schema-2 source and
  actual-configuration bindings. Do not hand-patch generated SystemVerilog.
- Configure ignored `cpu/toolchain.local.json` from the native or WSL example.
  Run `scripts/newpc.ps1` from cpu: Doctor, Emit, Unit, Functional,
  CoreMark; PdsPrepare/PdsCheck/PdsSynthesis cover the portable PDS test project.
- No new Verilog/SystemVerilog function. PDS-critical control selectors use
  constant indices; regular generate/reset loops remain allowed, below 2000
  iterations each. A control edit needs RTL tests and ADS retention inspection.
- Keep .pds, constraints, firmware source and deterministic preparation scripts
  in Git. work/, tool caches and machine-specific configuration stay ignored.
- Do not overwrite historical validation claims with current unverified results.
  Calibration simulation, synthesis, routed STA and board measurements differ.
- Record V3.1 CoreMark only after three performance and one validation runs,
  each timed for at least ten target seconds and bound to final RTL and firmware.
  The source test SoC reads CPU mcycle; integrated SoC reads SYS CLINT mtime.
  Keep each result and clock denominator separate. A release frequency needs
  final integrated-SoC slow/fast routed STA; synthesis or old V3 reports do not
  establish it. V3.1 integrated-board CoreMark was separately measured on
  2026-10-08; no new V3.5 board validation or Linux boot is assumed.
- Never access or modify Codex runtime log databases for this task. Use bounded
  tests, compact logs, and explain duration/stop method before long runs.
