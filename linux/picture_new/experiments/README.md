# Unselected offline experiments

`geometry_reduce_exact.h` and its numeric test preserve the ordered integral
reduction bits, but do not provide a consistent measured improvement. The r06
experiment found about 2–3% lower QEMU process CPU cost on three saved inputs,
about 4% higher on the cropped input, and higher host cost. They are not included
by production code or any delivered worker. See
`scripts/bench_picture_geometry_reduce.py` and the r06 investigation report.

The original tested input bytes are archived privately before this path-only
relocation. Future runs use this directory; old ELF identities remain bound to
their archived inputs.
