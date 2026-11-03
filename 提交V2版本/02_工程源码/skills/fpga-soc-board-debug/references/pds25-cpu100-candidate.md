# PDS25 CPU100 candidate: evidence boundaries (2026-11-01)

This is a failed/unfinished candidate case, not a release qualification.

- Positive routed STA and zero-weight synthetic cache tests did not establish
  official NNUE correctness. CPU100 full-pipeline evaluation reproduced an
  integer mismatch: bucket11 hardware2951 versus CPU2392. Pure CPU and StageA
  plus CPU-tail paths passed the same golden vectors. Do not infer a root cause
  from the frequency alone or classify CPU fallback as accelerator acceptance.
- PDS25 configuration may exit0 after native `No cable` errors. Preserve each
  attempt and require the real chain ID, programming success and DONE1. This
  session used PG2L100H ID00602899 and1MHz JTAG; these are project-specific.
- A4096-byte raw-UART probe passed but the larger transfer did not confirm its
  final SHA256. Prefer a verified SD/network path; small-probe success is not
  proof of sustained transfer integrity. Do not send binary past a receiver's
  timeout, and do not diagnose a kernel hang from missing serial output alone.
- The100MHz GUI retained its strict build-time frequency check. Paired software
  used CPU/DT timebase100MHz, physical SYS/CLINT49.5MHz and SBI ratio99/200.
  Rebuild/rebind the loader's payload CRCs and rootfs runtime manifest together.
- First-frame polling initially expired while the launcher was still running
  model SHA256 checks. Inspect the actual PID, executable, child and wait state;
  allow checks to finish rather than removing checks or starting a duplicate.
  A later independent check confirmed PID72 and the first-presented marker.
  That marker is a register submission, not physical display/user acceptance.
- Keep mutable handoff/current-status records outside sealed evidence lists,
  or snapshot them first. If such a record is refreshed, retain the old manifest
  and disclose expected/actual hashes separately; never rewrite raw failures.
- An explicitly requested candidate export may contain the bitstream, matching
  SD files, source and reports with `CANDIDATE_NOT_RELEASE` and known failures.
  It does not authorize calling failed hardware accepted or merging it into main.

Evidence case: `G:/fpga/build/pds25-cpu100-20261031-01/`, including
`BOARD_RESULTS_20261101.md`, `gui100-sd-01/session.json` and the native receipts.
During a user's live GUI test, preserve the running application and its logs.
