"""Integration checks for the current SoC's optional audio kernel build."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VoiceHardwareContract(unittest.TestCase):
    def test_current_dts_has_audio(self):
        source = (ROOT / 'linux/soc.dts').read_text(encoding='utf-8')
        self.assertIn('compatible = "pango,audio-capture-v2";', source)
        self.assertIn('reg = <0x1fe00600 0x00000100>;', source)

    def test_audio_driver_check_uses_current_project_paths(self):
        source = (ROOT / 'scripts/test_linux_audio_driver.ps1').read_text(encoding='utf-8')
        self.assertIn("linux\\soc.dts", source)
        self.assertIn("linux\\soc_defconfig.fragment", source)
        self.assertNotIn('cpu_v2.dts', source)

    def test_kernel_builder_can_include_audio(self):
        source = (ROOT / 'scripts/build_linux_mac_kernel.ps1').read_text(encoding='utf-8')
        for text in ('[switch]$IncludeAudio', '[string]$LinuxArchivePath',
                     'drivers/misc/pango_audio.c', 'include/uapi/linux/pango_audio.h',
                     '--enable PANGO_AUDIO_CAPTURE', 'CONFIG_PANGO_AUDIO_CAPTURE=y',
                     "linux\\soc.dts"):
            with self.subTest(required=text):
                self.assertIn(text, source)


if __name__ == '__main__':
    unittest.main()
