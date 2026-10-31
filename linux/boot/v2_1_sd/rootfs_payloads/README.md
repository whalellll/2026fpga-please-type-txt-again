# V2.1 GUI rootfs rebuild inputs

`picture/` contains additional **unvalidated candidate source inputs** for the
Picture wrapper/config/file stub. The seven binaries at this directory's top
level retain the exact release identity below. New target GUI/capture binaries
are built separately and injected by `scripts/make_picture_rootfs.ps1`; no
historical payload is overwritten. See `docs/PICTURE_INPUT.md`.

`picture/pcm/` adds 37 Chinese TTS fragments (1,524,000 bytes total), raw
16 kHz s16le mono. Its manifest records source voice, original/spoken text and
each SHA-256; the rootfs candidate helper checks identities before embedding.
They are generated speech assets, not camera data. Board playback is pending.

These seven files are byte-identical copies of the binaries used to build the
board-tested `linux/boot/rootfs.cpio`. The external PFF1 is
`linux/boot/pikafish.pff`, so it is not duplicated here. The baseline archive,
overlay and `scripts/make_rootfs.ps1` are also in this package.

The extracted-package verifier calls `make_rootfs.ps1` with
`-IncludePikafish -ExternalPff1 -SkipDtbUpdate` and these exact payloads. The
rebuild must equal SHA-256
`0470b510ad45b6b9dd394aea8f174825238158ff76dbd31a37d18ac22329a763`.
`linux/boot/soc.dtb` is separately bound to the SD loader's CRC32 contract.
