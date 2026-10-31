"""Verify generated raw speech inputs against vocabulary and PCM contract."""
import hashlib
import json
import re
import struct
from pathlib import Path

root = Path(__file__).resolve().parent.parent
directory = root / "linux/boot/v2_1_sd/rootfs_payloads/picture/pcm"
manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
source = (root / "linux/vision/xq_speech.c").read_text(encoding="utf-8")
vocabulary = re.findall(r'"([a-z_]+)"', source.split("xqs_names[XQS_COUNT]={", 1)[1].split("};", 1)[0])
assert manifest["contract_version"] == 1
assert (manifest["format"], manifest["sample_rate"], manifest["channels"]) == ("s16le", 16000, 1)
assert set(manifest["files"]) == {name + ".pcm" for name in vocabulary}
assert {p.name for p in directory.iterdir()} == set(manifest["files"]) | {"manifest.json"}
total = 0
for name, record in manifest["files"].items():
    data = (directory / name).read_bytes()
    assert len(data) == record["bytes"] and 0 < len(data) <= 320000 and not len(data) % 2
    assert hashlib.sha256(data).hexdigest() == record["sha256"], name
    assert not data.startswith(b"RIFF"), "WAV container supplied in place of raw PCM"
    samples = struct.unpack("<%dh" % (len(data) // 2), data)
    assert max(abs(s) for s in samples) > 100, name
    total += len(data)
assert manifest["files"]["rook.pcm"]["spoken_text"] == "居"
print("PICTURE_SPEECH_ASSETS_TEST_PASS clips=%d bytes=%d board_validated=false" % (len(vocabulary), total))
