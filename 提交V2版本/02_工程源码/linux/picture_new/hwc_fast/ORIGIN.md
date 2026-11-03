# Private HWC detector seam

`integer_hwc.c`, `integer_hwc.h` and `integer_bench.c` preserve the provider
snapshot bytes (aa134da06b404ee572976c438387c2f8aa3a2c96, implementation
da0f914e08fbcdb7678a0b76cfdbe84fd349e6f7). They came from the verified
software-integer-ops-aa134da-20261025.zip, whose whole-archive SHA256 is
f1ddf747e02898387fe712616f80c272b521243ebbb3ae3e724c9c532f4d6a05.

| File | SHA256 |
|---|---|
| integer_hwc.c | ba0cbd8dc0540a2a3f0c1f5e4137d04a7ca1d15bb81a155dc751642a35b68ecc |
| integer_hwc.h | 1b3056777a184db2e6d1adebef6067569dde54dd945669161da74fbb43545532 |
| integer_bench.c | 7b22d22707d00bd43fecc95d792d845d7b5466dfc990ae89f85daf895f01e67c |

`adapter.c/.h` bind the frozen r14 XQM/XQI pair, connect the existing NCHW F32
input and three-head output boundaries, and use the frozen quantizer. The
product never links the host mock or benchmark main. HWC activation is an
explicit e42 build option; unsupported capability, cancellation, allocation
failure or ioctl failure cannot fall back to CPU convolution.

`tests/` contains host-only device and independent-reference checks adapted
from the delivered tests. Its scalar dots emulate hardware for functional
comparison; their timing is not hardware evidence. `kit_host.c`, converter and
Python wrappers build the separate T4a handoff. They are not product objects.
The kit includes its own source/command/provenance manifest and synthetic-only
selftest. See KIT_README.md for the training-side boundary and numeric lineage.
