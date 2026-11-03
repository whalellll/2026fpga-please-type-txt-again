# Optional ISA plus frequency/accelerator candidate merge (PDS25 case)

The 2026-11-01 joint implementation is CPU `b1164e4`, SoC `4253258c`, native
run `75198114550743ada4e4015ad5cbf4e2`. It combines the accepted120MHz CPU
timing repairs, optional standard Zbc, and the final eight32-bit true-dual-port
FC1 repair. These identifiers are a case study, not defaults for other projects.

- Preserve both parent histories and exact Chisel/config/generated core+sim
  pairing. Default-off ISA support must reproduce the previous core bytes;
  profile-enabled firmware and its compiler report must name the actual ISA.
- Keep all six official CoreMark algorithm files unchanged. Changing the
  compiler profile requires a profile-specific verifier while retaining the
  baseline profile. Use fresh matched3+1 runs, full CLINT ticks, >=10seconds,
  independent official-C final CRC and the all-sample/MHz rule. Here baseline
  all-four5.281638583 -> joint5.910712298/MHz; total score is not a gate.
- A later FC1 fix cannot be omitted because the CPU-only branch already has
  passing STA. The actual joint RTL needs fresh synthesis, native bank-mode
  inspection, full PnR, all-corner STA and actual official model/concurrency
  acceptance. This run passed slow CPU setup/hold +0.204/+0.121ns and fast
  +3.144/+0.089ns, physical31sites/165pins/23priorities/20maxskew.
- Parse primitive pin directions by the actual vendor cell. `GTP_APM_E2.Z`
  is an input; `GTP_LUT*.Z` is an output. Shared arithmetic input buses must
  not become duplicate drivers. A parser repair must still reject genuine
  duplicate LUT drivers, and must not turn arithmetic results into arbitrary
  proof cuts. Bind the vendor model and adapter hashes.
- When synthesis removes a named architectural input such as `io_flush`,
  do not supply zero or silently drop the cofactor. Prove the exact generated
  source connection and actual retained parent/Ctrl FF wiring before mapping
  that one boundary. Keep all other unknown state rejecting and exercise a
  missing-flush mutation. Locate renumbered PMA nets through actual consumer
  pins and prove the entire original address function with SAT.

Evidence is under the joint run's `RESULTS.md`, `board-acceptance.json` and the
portable `docs/validation/cpu120-zbc-fc1-20261101/` export. CPU134/49suites,
architecture9, native qualification and board tests have distinct receipts.
Limited native-cone proofs are not whole CPU sequential equivalence. NNUE
cold/warm200 means14.862/13.959ms; the10ms target remains unmet. Formal ZIP,
independent extraction/regression and hash-bound media completion are separate.

## Package closure and current-version final-board waiver

The final package independently passed CPU134/49 suites, architecture9,
SoC/CDC/console and38 actual vendor FC1 cases with all packaged files unchanged.
Global Git `*.log` ignores must not remove raw accepted UART/proof logs: verify
the complete export-index closure and tracked evidence before creating a ZIP.
On Windows, use extended paths for historical long filenames and a short
workspace-local regression output for dependency-cache copies. Relocate exact
historical template prefixes, then test the real extraction path under
`G:/fpga/build`; a broad build-directory rejection also rejects valid new paths.
Check nested PowerShell helper dependencies before starting expensive suites,
and execute the console/vendor path preflights on the actual exported tree.

For this version the user explicitly requested no final actual-board recheck.
The per-version waiver is bound to the final ZIP, while earlier actual board,
matched CoreMark, official models, SD8 and user GUI/mouse receipts stay intact.
Do not report waived final SD8/CID/CRAM/direct-SD/application repeats as new
passes. Preserve the completed independent offline regression. A later
completion/skills documentation commit does not change the accepted ZIP or
its frozen implementation/source publication identities. Earlier versions'
waivers are not inherited. H was unavailable: G originals remain, removed0.
