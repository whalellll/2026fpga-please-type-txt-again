# Official Pikafish NNUE decode (host)

Decode `xiangqi_oss/Pikafish/pikafish.nnue` (ZSTD) into a fully decoded `PFF1`
model plus Stage A `PFA1` and Stage B `PFB1` packs that the board bring-up code
can bind.

## Quick start

```powershell
cd performance_soc_linux/sw/pikafish_official_decode
.\run_accept.ps1
```

Requires Python 3 + `zstandard` (`pip install zstandard`).

## Outputs (`out/`)

| Artifact | Role |
| --- | --- |
| `artifacts/pikafish.nnue.flat` | `PFF1` runtime image: no ZSTD and no LEB128 decoding |
| `pikafish.nnue.raw` | ZSTD-unpacked official stream, retained for compatibility checks |
| `manifest.json` | Hashes, dims, file list |
| `ft_biases.i16.bin` | FT bias, LEB128-decoded |
| `ft_psq_weights.i8.bin` | HalfKA rows × L1=1024 (feature-major) |
| `ft_threat_weights.i8.bin` | Threat rows × L1 |
| `ft_psqt.i32.bin` / `ft_threat_psqt.i32.bin` | PSQT tables |
| `official_psq.pfa1` | Stage A pack (PSQ only) |
| `official_threat.pfa1` | Stage A pack (threats; ~46 MiB weights) |
| `mlp_stack00.pfb1` … `mlp_stack15.pfb1` | Stage B MLP per layer-stack |
| `artifacts/pikafish-stageb-mac.bin` | 16 个层栈的 593,920 B MAC 原生布局总包 |

## PFF1 no-decompression image

`pikafish.nnue.flat` is the board runtime model. Its 4096-byte header contains
the official version/structure hashes, dimensions, the SHA-256 of the
ZSTD-unpacked official stream, and six page-aligned section descriptors. Each
descriptor has a byte length and CRC32.

| Section | Contents |
| --- | --- |
| `FTBI` | 1024 signed 16-bit feature-transformer biases |
| `FTTW` | threat feature weights, signed 8-bit file/scalar order |
| `FTTP` | threat PSQT, signed 32-bit little-endian |
| `FTPW` | HalfKA/PSQ feature weights, signed 8-bit file/scalar order |
| `FTPP` | HalfKA/PSQ PSQT, signed 32-bit little-endian |
| `MLPS` | all 16 fixed-size MLP stacks, bias then weights for each layer |

The image deliberately contains no compressed payload. The Linux loader only
needs fixed-size reads/copies and CRC validation; it must not call ZSTD or the
LEB128 decoder. `verify_flat_nnue.py` independently checks every descriptor and
CRC, compares the raw-stream SHA-256, compares all five feature-transformer
arrays, and compares every byte of all 16 MLP stack payloads.

## Verified by decoder

- File `Version == 0x6A448AFA`
- Structure hash matches Pikafish `Network::hash`
- FT + all 16 stack headers
- Entire decompressed stream consumed (no trailing bytes)

## Limits (not bit-exact vs AVX2 Pikafish yet)

1. **FT Packus permute** — export is file/unpermuted order (identity order used by
   non-AVX builds). AVX2 runtime permute is not applied.
2. **MLP layout** — weights are official **file order**, treated as Stage-B
   row-major `W[out][in]`. Matches the conceptual index used when writing the
   net; SIMD memory scramble is the inverse of that serialization.
3. **Pair activations** — Stage B concatenates `[SqrClipped \| Clipped]`.
   AVX2 builds may interleave activations and pre-permute fc1/fc2 weights.
   Scores need a golden vector from Pikafish before claiming eval parity.
4. **PSQT / stack select** — exported but not fused into Stage B score yet.
5. **Threat + HalfKA feature indexing** — decode only; feature list generation
   from a xiangqi position is a later stage.

## Stage B accelerator pack

From the repository root, run:

```powershell
.\scripts\build_pikafish_stageb_linux_wsl.ps1 -Distro pikafish-verify
```

The generator converts every fc0 matrix from row-major PFB1 order into the exact
four-tile byte order consumed by the current MAC and exhaustively reverses every
index before emitting the pack. The 16 fixed-size slots plus headers occupy
`0x91000` bytes inside the existing 1 MiB accelerator window. Linux validates
the container and per-slot CRCs, copies it to bus address `0x1b000000` through
the CPU uncached alias `0x9b000000`, and verifies readback. The prepacked backend
can point fc0 directly at a resident slot; wiring the official Pikafish evaluator
to that backend remains separate work.

## Size note

The ZSTD-unpacked official stream is 66,082,730 bytes. The PFF1 image is
68,122,688 bytes (64.97 MiB), including its 4 KiB header and page-alignment
gaps. Threat weights alone occupy `45547 * 1024` bytes. Keep the component
files under `out/` local; promote only the single verified PFF1 image into the
Linux runtime.
