import gzip
import json
import tempfile
import unittest
import subprocess
from pathlib import Path

from prepare_picture_candidate import identity, tokens
from prepare_picture_sd_candidate import stage, install_contract


class SdCandidateTest(unittest.TestCase):
    def test_namespaced_gzip_and_clock_keep_original_release(self):
        current = Path(__file__).resolve().parent.parent
        # This stages the historical5f802 contract, not the current CPU80 image.
        # Restore its real Git objects into a disposable fixture; never fake a SHA.
        current_files = [current / "linux/boot/soc.dtb", current / "linux/boot/rootfs.cpio"]
        before = [identity(p) for p in current_files]
        with tempfile.TemporaryDirectory(dir=current / "build") as tmp:
            repo = Path(tmp) / "historical-5f802-fixture"
            for name in ("artifacts/soc_top.sbit", "linux/boot/soc.dtb", "linux/boot/fw_jump.bin",
                         "linux/boot/Image", "linux/boot/rootfs.cpio", "linux/boot/pikafish.pff", "linux/boot/pikafish.atk"):
                target = repo/name
                target.parent.mkdir(parents=True, exist_ok=True)
                frozen=current/'prebuilt/picture-sd-7f0ba644'
                if (frozen/'manifest.json').is_file():
                    import hashlib
                    manifest=frozen/'manifest.json'
                    self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),'9f592ff96e1665401783f18917d27cb1f3146a00ba819310b9ca0fea6a639bf6')
                    record=json.loads(manifest.read_text())
                    blob=(frozen/name).read_bytes()
                    self.assertEqual(hashlib.sha256(blob).hexdigest(),record['files_sha256'][name])
                    target.write_bytes(blob)
                else:
                    target.write_bytes(subprocess.check_output(["git","show","7f0ba644:"+name],cwd=current))
            (repo/"build").mkdir()
            originals = [repo / "linux/boot/soc.dtb", repo / "linux/boot/rootfs.cpio"]
            output = repo / "build/candidate"
            result = stage(repo, originals[1], output, "P17", "jiffies")
            self.assertEqual(len(result["files"]), 6)
            self.assertNotIn("brfs2.bin", result["files"])
            self.assertNotIn("br.dtb", result["files"])
            self.assertEqual(gzip.decompress((output / "P17FS.BIN").read_bytes()), originals[1].read_bytes())
            _, props, _ = tokens((output / "P17.DTB").read_bytes())
            self.assertIn(b"clocksource=jiffies", props["/chosen/bootargs"][0])
            self.assertIn("/reserved-memory/clint-mmio@2000000/no-map", props)
            self.assertIn("/reserved-memory/snapshot@1b600000/no-map", props)
            # Installation binds the exact existing loader bytes, all four new
            # files, card geometry, and matching padded FAT names.
            (output / "loader-picture-candidate.bin").write_bytes(b"reviewed loader fixture")
            install = install_contract(repo, output, 62333952, 32)
            self.assertEqual([e["name"] for e in install["files"]],
                             ["P17FS.BIN", "P17.DTB", "P17BOOT.BIN", "P17.JSN"])
            for entry in install["files"]:
                self.assertEqual(identity(Path(entry["path"]))["sha256"], entry["sha256"])
            header = (output / "picture_install_payloads.h").read_text()
            self.assertIn('"P17BOOT BIN"', header)
            self.assertFalse(json.loads((output / "P17.JSN").read_text())["sd_written"])
            # Preserve the historical16MiB bound; a modern larger initrd is not
            # a valid positive fixture for this older namespaced contract.
            oversized = repo / "build/oversized.cpio"
            oversized.write_bytes(b"070701" + bytes(0x01000000 + 1 - 6))
            with self.assertRaises(ValueError):
                stage(repo, oversized, repo / "build/oversized-output", "P17", "jiffies")
            self.assertFalse((repo / "build/oversized-output").exists())
            with self.assertRaises(ValueError):
                stage(repo, originals[1], output, "P17", "jiffies")
            with self.assertRaises(ValueError):
                stage(repo, originals[1], Path(tmp) / "invalid", "LONG5", "riscv")
        self.assertEqual(before, [identity(p) for p in current_files])


if __name__ == "__main__":
    unittest.main()
