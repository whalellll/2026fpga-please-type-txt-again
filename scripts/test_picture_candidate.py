import struct
import unittest
from pathlib import Path
from prepare_picture_candidate import snapshot_dtb, tokens, prepare
import tempfile


class CandidateTest(unittest.TestCase):
    def test_existing_clint_reservation_cannot_be_weakened(self):
        repo = Path(__file__).resolve().parent.parent
        blob = bytearray((repo / "linux/boot/soc.dtb").read_bytes())
        header, props, _ = tokens(blob)
        _, position = props['/reserved-memory/clint-mmio@2000000/reg']
        struct.pack_into('>II', blob, header[2] + position, 0x02000000, 0x1000)
        with self.assertRaisesRegex(ValueError, 'conflicting existing reservation'):
            snapshot_dtb(blob, 9000000)
    def test_background_banks_are_reserved_only_when_requested(self):
        base = (Path(__file__).resolve().parent.parent / "linux/boot/soc.dtb").read_bytes()
        _, legacy, _ = tokens(snapshot_dtb(base, 9000000))
        _, background, _ = tokens(snapshot_dtb(base, 9000000, True))
        name = '/reserved-memory/camera-capture@1b800000/'
        self.assertNotIn(name + 'reg', legacy)
        self.assertEqual(background[name + 'reg'][0], struct.pack('>II', 0x1b800000, 0x400000))
        self.assertEqual(background[name + 'no-map'][0], b'')
        self.assertEqual({key: value[0] for key, value in legacy.items()},
                         {key: value[0] for key, value in background.items() if not key.startswith(name)})

    def test_background_contract_requires_completed_hardware_gates(self):
        repo = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'audited hardware build'):
                prepare(repo, repo / 'linux/boot/rootfs.cpio', Path(folder), True)

    def test_kernel_ram_allocator_cannot_use_clint_mmio(self):
        base = (Path(__file__).resolve().parent.parent / "linux/boot/soc.dtb").read_bytes()
        _, props, _ = tokens(snapshot_dtb(base, 9000000))
        protected = False
        for name, (value, _) in props.items():
            if not name.startswith('/reserved-memory/') or not name.endswith('/reg') or len(value) != 8:
                continue
            address, length = struct.unpack('>II', value)
            if address <= 0x02000000 and address + length >= 0x02010000:
                protected = name[:-3] + 'no-map' in props
        self.assertTrue(protected, 'CLINT lies inside the RAM bank and must be excluded from kernel page allocation')

    def test_preserve_existing_properties_and_reserve(self):
        base = (Path(__file__).resolve().parent.parent / "linux/boot/soc.dtb").read_bytes()
        output = snapshot_dtb(base, 9000000)
        _, props, _ = tokens(output)
        self.assertEqual(props["/reserved-memory/snapshot@1b600000/reg"][0],
                         struct.pack(">II", 0x1b600000, 0x200000))
        self.assertEqual(props["/chosen/linux,initrd-end"][0], struct.pack(">I", 0x3000000 + 9000000))
        with self.assertRaises(ValueError):
            snapshot_dtb(output, 9000000)
        for size in (0, -1, 0x1000001):
            with self.assertRaises(ValueError):
                snapshot_dtb(base, size)


if __name__ == "__main__":
    unittest.main()
