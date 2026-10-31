Matched CPU60 runtime inputs only. This is not a complete bootable SD kit or a formal delivery.
Do not combine the new voice CNN with the old SD77 autostart.
The three Picture_new graph/weight files remain deferred; the interface executable fails closed without them.
The dedicated Pikafish programs use the existing official PFF1/attack assets and new paired kernel.
Existing SD/Flash and linux/boot production files were not overwritten.
See docs/Integrated60_20261024.md and the native physical receipt for sbit/STA status.

Voice entry points after installing these files and the matching kernel:
  xqvoice-small-cnn balanced24.bin input.wav /tmp/voice.trace mac wav
  xqvoice-small-cnn --worker balanced24.bin mac /dev/null
The worker uses the pinned XQW1 request/result protocol over stdin/stdout. It opens /dev/pango-voice0; it does not call the retired generic dense engine.
Picture interfaces after supplying the deferred trained graphs:
  picture-new-infer board board.xqm board-input.f32 board-output.f32
  picture-new-infer detector detector.xqm detector-input.f32 detector-output.f32
  picture-new-infer classifier classifier.xqm classifier-input.f32 classifier-output.f32 3
