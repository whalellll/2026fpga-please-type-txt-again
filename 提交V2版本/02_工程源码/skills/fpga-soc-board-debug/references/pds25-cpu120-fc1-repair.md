# PDS25 CPU120 FC1 repair and SD boot acceptance

The 2026-11-01 candidate07 uses SoC implementation13ea2329 and CPU8c14579,
native run b4dc02253edf402ea26104f106505857. All124 final all-corner rows pass;
the board bitstream SHA256 is c641cf7ea2897102f87cd6081a92ef3b2ed4802089756c33bc1302483931ef82.
This record describes completed implementation/board checks. Formal package
completion still requires its independent regression and ZIP-bound SD boot.

An earlier candidate's full NNUE mismatch was exactly explained by replacing
every odd FC1 row with its preceding even row: all32 official vectors and the
initial2951-versus2392 score agreed with that independent diagnosis. Native
PDS25 packed adjacent inferred FC1 banks into72-bit SDP memories. Eight explicit
32-bit true-dual-port DRM36K banks restored all65 independent official board
cases and the initial2392 result. Preserve actual native mode/readback evidence;
DBW/DBR flags are TRUE in this working32-bit configuration and must not be
mistaken for the original72-bit SDP configuration.

For PG2 DRM36 primitives, address bit15 must be1 for chip select even when
cascade mode is NONE. Bind GTP_GRS in vendor primitive simulations. The failed
zero-chip-select prototype and missing-GRS attempt remain separate evidence.

An SD kit can load all files with correct CRCs and still truncate userspace:
its DTB initrd-end must equal initrd-start plus the actual CPIO length. Verify
independent CPIO metadata, runtime hashes, both NNUE aliases and FDT bounds.
Candidate07 uses36487680 bytes at50331648, ending86819328. Do not rewrite the
earlier verifier's incorrectly broad PASS; invalidate that kit explicitly.

CPU120 uses SYS/CLINT49.5MHz and SBI33/80. NNUE timing uses a readonly CLINT
wrapper,21ns reported resolution. Cold/warm200 means14.852/13.937ms are correct
hardware measurements but still miss10ms. Concurrent image/NNUE/voice/5s audio
passes correctness and80000 samples with0overflow, with substantial latency
inflation retained in raw logs. The user explicitly waived CoreMark comparison;
the actual three performance and one validation runs, CRCs and clocks remain.

Restore an interactive GUI in a fresh session (`setsid`, explicit input/output
redirection). An inherited shell job can stop on SIGTTOU during tty operations
even with stdout redirected. Verify the real GUI/worker executables and states,
terminate only confirmed owned processes, and confirm a new first frame and
service processes. User confirmed display and mouse normal after restoration.

PDS25 native checks must follow actual exports and producers. The qualified
limited contracts include the original85760 frontend/10240 return vectors,
binary64FF ROB owner state with all original write/read oracles, actual packed
UART DP/X4 storage, full data/instruction classification, both immediate RsMem
classifier next states,50Gray D/actual-CE SAT proofs and48CDC selectors/tags.
Opaque arithmetic data outputs in the classifier proof are symbolic values;
they do not certify arithmetic implementation. CPU131/architecture8 regression,
final physical timing and board tests remain distinct gates.

Evidence entry: build/pds25-cpu120-20261101-07/board-state-current.json,
tool-qualification-01/result.json and BOARD_RESULTS_20261101.md in the workspace.
