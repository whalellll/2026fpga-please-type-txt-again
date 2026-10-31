# R29 fixed engineering inputs

These are unchanged build inputs of the user-selected R29 recognition worker.
The three native `.xqm` packs already exist under `artifacts/main70_20261027/model-source/native_int8/` and are referenced rather than duplicated.
Only the missing frozen detector HWC layout, refinement random table and parameter header are stored here. `manifest.json` records their original package, byte lengths and SHA-256 identities. They contain no camera photos, requests, board positions, evaluation samples or training checkpoints.

From WSL with the existing RV32 musl toolchain at `/opt/toolchain/bin/`, run:

```sh
sh linux/picture_new/build_r29.sh "$PWD" "$PWD/build/r29-local"
```

The entry copies the six checked inputs to the new output directory and invokes the existing production builder with the frozen R29 flags. It never overwrites an existing output directory or accesses hardware. A new build was explicitly skipped at the user's request during this cleanup; the existing restored-source R29 byte-exact receipt remains historical evidence, not validation of this newly added convenience entry.
