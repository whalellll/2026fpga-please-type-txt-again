# Mapped CPU/SYS CDC and CLINT tests

`run_mapped_gate_tests.ps1` uses an already synthesized integrated SoC ADS VM.
It never invokes PDS. It requires the VM, passing CDC ADS audit, and frozen
input snapshot to share one run ID and matching SHA-256 hashes. It also checks
the frozen CLINT and CDC RTL hashes against this checkout before compilation.

After the final main build is selected and its own ADS VM is available, run
the structural preflight and then the bounded gate test from the SoC root:

```powershell
$gateRunId = '<final-32-digit-run-id>'
$gatePds = Join-Path (Get-Location).Path 'pds'
$gateArgs = @{
    Vm = "$gatePds\synthesize\soc_top_syn.vm"
    Snapshot = "$gatePds\input-snapshots\$gateRunId\snapshot.json"
    CdcAuditJson = "$gatePds\input-snapshots\$gateRunId\cpu-sys-cdc-ads.json"
    ExpectedRunId = $gateRunId
    ResultDirectory = "artifacts\selftest\mapped-gate-$gateRunId"
}
.\sim\run_mapped_gate_tests.ps1 @gateArgs -PreflightOnly
.\sim\run_mapped_gate_tests.ps1 @gateArgs
```

Preflight verifies the current mapped B/R FIFO module types, positional port
order, retained RAM bits, CLINT input ports and 64 mapped mtime registers. The
divisor-15 VM places an unrelated SD I/O decode LUT in the CLINT module;
preflight checks that its five extra inputs feed only that LUT, and the isolated
testbench ties them low. If
ADS changes the interface, it stops and names the mismatch so the testbench
can be adapted to the actual VM. It does not reuse a previous PASS marker.

The run has a five-minute wall deadline; each Icarus compile is limited to
60 seconds and each simulation to 30 seconds. The owner PowerShell PID is
printed before the first child. End that process to stop its Windows Job
children early. A new result directory is required for every attempt; it
retains stdout/stderr, the exact command lines, VM and testbench hashes, and
`result.json` only on complete PASS. The runner inventories all 319 installed
Pango vendor `.v` models in `vendor_models.sha256`, hashes the inventory and
both Icarus executables in `result.json`, and checks these inputs again after
simulation. A changed model set or changed input fails the run.

The selected B and R mapped FIFO submodules are checked at three independent
clock ratios/phases with seeded backpressure, payload ordering, stalls,
two-stage Gray synchronization, and reset with pending data. Whole-SoC ADS
optimization retained one B payload bit and 36 R payload bits in the reviewed
shape. The CLINT mapped gate test checks two ordinary writes and zero-strobe
writes to both mtime words, including a low-to-high rollover.

This is zero-delay functional simulation using installed Pango GTP primitive
models. It has no SDF or metastability model and does not cover the whole AXI
interface, route, board, or final timing acceptance. The e526 old VM was used
only as a negative CLINT fixture: it failed on the zero-strobe rollover write.
Candidate c476 PASS results remain development evidence until the selected
final main VM is rerun and its own run-specific result is reviewed.

The final main divisor-15 run `6e934e9f84094159bff9a8870e260e8e` passed
preflight and all six B/R FIFO cases and four CLINT writes. Its mapped VM hash
is `a92aafcc8fd5a4b03338568540cec75d35682fb1f2149aeb0b8cb5c67391c135`.
The run-specific result is
`artifacts/selftest/mapped-gate-6e934e9f84094159bff9a8870e260e8e/result.json`
(SHA-256 `a3ae7976f37a92784e1ac6652a4277369fa56fb8b4e8be6b44642291a886ccfb`).
All 349 files in its frozen input snapshot still match their recorded hashes.
