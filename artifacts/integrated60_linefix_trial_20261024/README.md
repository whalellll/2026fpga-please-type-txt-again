# CPU60 functional trial — STA failed, targets unmet

This is the exact native4 `9ba02f10` CRAM image tested with streamed voice,
original Picture_new models and official Pikafish. Final SYS hold is
−0.029ns slow/−0.017ns fast. The user authorized functional testing despite
timing failure, then authorized a temporary remote branch after testing.
This is not a formal release or permission to write configuration Flash.

Full measurements and scope: [joint board report](../../docs/Integrated60_Joint_Board_20261024.md).
`manifest.json` preserves the pre-board physical candidate identity; subsequent
board results and push state are separate receipts, never edits to native STA.

`sd-inputs/` saves the exact six trial runtime payloads, original software
manifest and18 loader logs. The two official NNUE files reuse `linux/boot/`.
Recreate all eight files in a new PC directory, without writing media:

```powershell
G:/py/ana/python.exe -X utf8 scripts/freeze_integrated60_trial_sd.py --materialize build/replay-trial-sd
```

The recreated software manifest retains its original CPU60 bitstream binding;
the joint board receipt separately proves compatibility with native4 by
406 identical hardware inputs and the single changed vision DMA boundary file.
The full native databases stay local at `G:/i60pnr4` for reproducibility;
this input snapshot is not a formal ZIP/delivery package.
