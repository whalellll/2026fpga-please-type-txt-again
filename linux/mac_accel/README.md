# Linux MAC scheduler

This directory contains the Linux ownership and scheduling path for the dense
MAC v2 accelerator and the Stage 2 convolution candidate.

## Linux ownership and ABI1 contract

- `pango_mac.c` binds `pango,mac-accel-v2` and is the only normal Linux owner
  of the MAC registers and physical DMA scratch area.
- Each successful `open("/dev/pango-mac0")` claims one of eight preallocated,
  zeroed, private 1 MiB page contexts. A ninth concurrent open returns
  `EBUSY`. `mmap` uses `remap_pfn_range()` on that context; the driver clears
  it again before reuse. The fixed pool avoids large allocations during
  concurrent opens on this RV32 Linux configuration.
  Separate threads should open separate file descriptors; a process may also
  share one descriptor when its own mutex covers packing, submission, and
  result consumption.
- Phase 1 copies every job's packed input/weight/bias ranges from the private
  shadow into physical scratch.  This is the correctness-first boundary; a
  later residency/cache-generation phase is needed to recover the old direct
  `/dev/mem` weight-residency performance.
- `PANGO_MAC_IOC_RUN` validates a job and serializes it with a device-wide
  mutex.  The driver copies only that job's source ranges into physical DDR,
  runs the accelerator, and copies the output to the caller's private shadow.
- The current RTL interrupt is observable but is not wired into a Linux CPU
  interrupt controller.  Phase 1 therefore polls with bounded timeout and
  periodic `cond_resched()`.  A later RTL/driver phase will add IRQ completion
  and an asynchronous priority queue.

The Pikafish runtime prefers this device and retains its legacy `/dev/mem`
backend only for transition testing with the existing production kernel.
Set `PIKAFISH_MAC_REQUIRE_DRIVER=1` when validating a scheduler-enabled kernel
so an unavailable driver cannot silently fall back to the unsafe path.

## Build and validate

Run:

```powershell
./scripts/test_linux_mac_scheduler.ps1
./scripts/build_linux_mac_kernel.ps1
./scripts/build_linux_mac_scheduler_test.ps1
```

The kernel build writes a candidate `Image`, DTB, and configuration under
`build/linux-mac-scheduler/out`.  It deliberately does not overwrite
`linux/boot`, modify the MicroSD card, or program FPGA/configuration Flash.
The build extracts the configuration embedded in the current production
`linux/boot/Image`, changes only the scheduler-related configuration, and
rejects a candidate that grows by more than 1 MiB.  This avoids accidentally
replacing the board kernel with the much larger generic RV32 defconfig.

After booting that candidate kernel, run `pango-mac-scheduler-test` as root.
It starts three processes with two threads each; every thread opens a separate
context and submits 64 data-distinct jobs.  The pass marker covers 384 jobs and
detects cross-context scratch corruption.

The 2026-09-21 MicroSD board run passed with:

```text
PANGO_MAC_SCHEDULER_TEST_PASS processes=3 threads_per_process=2 jobs=384
```

## Stage 2 convolution window candidate

`PANGO_MAC_IOC_RUN_CONV` uses ABI version 2 and the same private 1 MiB mapping
and device mutex as the legacy `RUN` ioctl. The driver validates the full
NHWC4 input, weight, and reserved output ranges before copying sources to the
physical scratch area. `WINDOW_ONLY` loads up to 32 packed 1024-bit weight
rows, activates the matching model/generation/tile bank, and streams one
channel tile through the convolution window. It returns source DDR bytes,
window taps, weight reuse, stalls, cycles, a tap XOR, and a weight read digest.
It does not write an output tensor. The old `OUTPUT_DST(0x24)` and legacy ABI1
remain unchanged. The capability bit reports ABI2 support only when the
`MCON` register block is present.

Run the focused RTL/UAPI suite with `bash scripts/test_mac_conv_stage2_dma.sh`.
Build the isolated kernel with
`scripts/build_mac_conv_stage2_kernel_candidate.ps1`; its output stays in
`build/vision/linux-mac-conv-stage2/out`. The current candidate kernel built
successfully and the legacy scheduler host checks passed. The matching full
SoC RTL passed simulation and volatile CRAM board tests for four convolution
window shapes plus the old dense MAC self-test. ABI2 Linux board execution
passed on 2026-09-29. Counters count engine-side DDR traffic and cycles; they
exclude Linux scheduling and shadow copies.

## Stage 2 compact compute candidate

Hardware `MCON` version `0x00030000` adds a compute command at control bit 4,
completion/error status at bits 8/9, compact output byte counter 12, and
compute cycle counter 13. Control bit 5 aborts the convolution engine and its
outstanding AXI transaction; the driver uses it on error or timeout. The old
`MCON` version `0x00020000` remains valid for ABI2 `WINDOW_ONLY` jobs.

The same `PANGO_MAC_IOC_RUN_CONV` structure accepts ABI version 3 with
`PANGO_MAC_CONV_FLAG_COMPUTE`. `reserved[0]` points to 16 signed INT32 biases
and `reserved[1]` to 16 right-shift bytes in the caller's private shadow.
The driver checks the source/output ranges, programs per-channel quantization,
serializes the one physical engine, waits for compact DDR completion, and
copies the S8 NHWC output bytes back to the shadow. The compute capability bit
is advertised only by hardware version 3. ABI1 dense MAC jobs and ABI2 window
jobs keep their layouts and behavior.

The current compute tile accepts Cin <= 4, Cout <= 16, one channel tile, and
K <= 128. Four signed byte multipliers update one output channel per cycle.
The 16-channel tile retains only the lower 512 bits of each packed weight row.
SiLU is a CPU postprocessing operation. For deeper K, the CPU
reference retains INT32 partial sums across segments and applies requant only
after the final segment; the present hardware rejects those descriptors.
`pango_mac_conv_compute_test.c` checks a 7x7, 6x6x3/stride 2/padding 2 job,
plus 1x1 pointwise and 3x3 stride-2/padding-1 jobs, against independent CPU
oracles and verifies DDR byte/window counters.
The static RV32 test program is added to the candidate rootfs by
`scripts/build_mac_conv_stage2_rootfs_candidate.ps1`. Kernel and rootfs
candidate builds pass. The source-matched SoC bitstream with SHA-256
`56ac5655b1923980df87120e84df4f4ce318caab6ef4b1ae1da1eb0a85706a92`
passed PDS setup and hold timing (slow-corner setup WNS +0.558 ns) and was
loaded by JTAG to volatile CRAM. Its bare-metal full first layer returned
409,600 S8 output bytes with CRC `eb240272`, 409,600 input DDR bytes,
3,456 weight DDR bytes, 921,600 taps, and 15,466,918 compute cycles. The
matching Linux Image, DTB, and candidate rootfs reached `/ #`; ABI2 window,
ABI3 compute, the eight-context pool, and the legacy scheduler board programs
returned
`PANGO_MAC_CONV_WINDOW_BOARD_PASS`, `PANGO_MAC_CONV_COMPUTE_BOARD_PASS`, and
`PANGO_MAC_SCHEDULER_TEST_PASS` (384 jobs). The first-layer raw board log is
tracked at `vision/evidence/stage2_compute_board_20260924.log`; the remaining
session logs are under the local `build/vision/mac-conv-compute-clean/`
directory. The later Stage 2 board acceptance, image hashes, shape metrics,
legacy Pikafish regression and serial logs are recorded in
`docs/YOLOv5n_Stage2_Board_Evidence.md`. The board candidate starts the GUI
manually from a no-autostart rootfs; automatic GUI startup with the final DTB
was not repeated. Fixed test vectors establish integer correctness and
engine-side measurements, not trained-model accuracy or 30 fps.
