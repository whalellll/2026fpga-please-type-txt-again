# CPU clock candidate boot support

V3.5 exposes CPU cycles through the TIME CSR, while CLINT MTIME runs at the
fixed 49.5 MHz SYS clock. The existing board firmware's 5/6 bridge is specific
to CPU 59.4 MHz. CPU 74.25 MHz requires 2/3; the dedicated 70.875 MHz
CPU PLL requires 44/63. CoreMark uses SYS CLINT directly
and retains its original boot ROM and GCC16.2 firmware.

`pg2l_timer_bridge.h` converts remaining intervals with a generated exact PLL
ratio, preserves the all-ones disable sentinel, and avoids arithmetic wrap.
`scripts/test_pg2l_timer_bridge.py` compiles this same C helper and compares
33,872 cases with an independent integer reference for shared divisors 12
through 18 and the dedicated 70.875 MHz profile.
The host test is arithmetic evidence; Linux scheduling needs board acceptance.

Build an isolated candidate under WSL (the output must not exist):

```sh
python3 linux/opensbi/build_clock_candidate.py \
  --output build/cpu-clock-boot-new \
  --archive linux/sources/opensbi-1.3.1.tar.gz \
  --clock-config config/clocks.json
```

Run this command from the isolated candidate/review root whose clock config
matches the selected hardware. The active development root can still retain
the older 59.4 MHz defaults. The upstream archive is SHA-256
`ee5be2c582f9a837e9db88368220758e014dd694b566bb6c8efe1e50cfad0004`.
Its license notices remain in the archive. Dependencies are the recorded WSL
GCC11.4 `riscv64-linux-gnu-` tools, GCC9.4 `/opt/toolchain/bin/riscv32-linux-musl-`
tools, make, patch and dtc/fdtput/fdtget. The helper validates ELF32/IMA ABI,
clock configuration, output hashes and unchanged inputs. It does not build
the release boot ROM, run FPGA tools, access UART/JTAG or write SD/Flash.

The loader source and audio DTS are taken from the separately identified
`artifacts/voice_hw_candidate_20261016/` candidate. Include its loader sources
and boot DTS when packaging this rebuild path. It retains read-only loading
and CRC checks for the existing six SD files. After loading, it publishes the
new OpenSBI/DTB in RAM using word stores to both cache aliases, checks CRCs,
and refuses to boot if the CPU/TIMEBASE MMIO frequencies differ. The generated
`boot-manifest.json` binds all inputs, compiler commands and outputs.

`BOOT_CANDIDATE_BUILT_NOT_BOARD_TESTED` is not Linux or performance acceptance.
Use a bitstream with matching final STA and current programming authorization.
