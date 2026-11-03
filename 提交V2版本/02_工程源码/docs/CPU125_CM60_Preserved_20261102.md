> Historical state below. Fresh routed STA/physical/bitstream now pass; board remains pending. See [current sbit and evidence](CPU125_CM60_Sbit_20261102.md).

# CPU125/CoreMark6.0 candidate preserved, 2026-11-02

The user answered `稍后连接，先保留候选`. No board connection or actual board
validation is attempted. The local candidate and all evidence remain on G.

The complete rebuilt CPU125 RTL diagnostics are6.031419124 performance and
6.011920910 validation CoreMark/MHz; both have correct independently checked
official CRC. These100-iteration/~0.133-second measurements are diagnostics.
Production automatic calibration still uses ITERATIONS=0. Five firmware
builds, CPU/source/clock binding,10 compiler-profile and11 capacity cases pass.

Fresh PDS2025.2 native synthesis/map run`42ad23ef557d4d13ba91500b8a680c59`
measures45787LUT/34226FF/1946LUTRAM/126.5DRM/76APM: **zero change in every
resource category**. Decrypted mapped primitive/config/control identity and
all1,048,576 boot data bits pass. The193-module text comparison explicitly
accounts for absolute FDC comments and re-encrypted vendor data; actual
decrypted leaf configuration/connection records must match literally.
Earlier failed raw-text comparisons remain preserved separately.

Implementation commit`a6e0009b`; integration freeze
`aac96d8ccf77f84d69747e96b448bc34421eaaa4` retains latest accepted main
`c3ecd03d` history. CPU is unchanged at`b1164e42737a081cc640a2113c76a53d0c91a97a`.
The local branch is`candidate/cpu125-coremark60-20261102-01`. Later metadata
commits do not change this frozen native implementation or CPU identity.

New PnR was **not started**. The waiter required8GiB free commit and2.5GiB
physical memory, with two stable samples; headroom remained below the commit
gate. Only this task's waiting Python process was stopped after verifying its
PID/command/creation/parent and the absence of any native-launch receipt.
Its wrapper's nonzero exit denotes this stopped wait, not a routing/STA failure.
No other processes or system settings were changed. The original pending
attempt/preflight/memory samples and stop receipt remain intact.

There is no active build from this task. Fresh final all-corner STA, physical
readback, new bitstream and board CoreMark3+1/official models/concurrency/SD
acceptance remain pending. Parent CPU125 WNS is not a result for the new ROM.
No remote push, main promotion, formal ZIP, board/SD/Flash write or cleanup.

Work directory:`G:/fpga/build/cpu125-coremark60-20261102-01`.
Read`status.json`, `RESULTS.md`, `frozen-inputs.json`, `native-identity-03/result.json`
and`pnr-wait-stop.json`. Original523 native and205 verification inputs remain
frozen and can be checked without starting tools:

```powershell
G:/py/ana/python.exe -X utf8 -B scripts/resume_cpu125_cm60.py --work G:/fpga/build/cpu125-coremark60-20261102-01
```

After inspecting actual process owners and sufficient memory, start a **new**
offline attempt while retaining old receipts:

```powershell
G:/py/ana/python.exe -X utf8 -B scripts/resume_cpu125_cm60.py --work G:/fpga/build/cpu125-coremark60-20261102-01 --run --attempt 2
```

The runner keeps39 actual priority nets,30 CSR sites,165 pin constraints,
strict7.992ns CPU/7.192ns CDC, seed3/decongestion4/hold200ps and four-CPU
affinity for its own PDS process. It creates`pnr-02/` and
`finish-native-flow02.json`, waits on the same memory gate, and then performs
full STA/physical readback/bitstream generation. It performs no board access,
push or release. Existing `docs/CPU_Frequency_Handoff.md` is part of the frozen
verification input snapshot; use this live preservation note and the workspace
root handoff for current status. Don't edit old source inputs or reuse a previous
attempt output path. All new sources/results/tmp remain under G:/fpga.
