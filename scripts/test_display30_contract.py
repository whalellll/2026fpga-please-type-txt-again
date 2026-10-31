"""Exercise real display/clock policy and reject mismatched physical clocks."""
import json
from pathlib import Path
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]

def check(root, okay):
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
               "$ErrorActionPreference='Stop'; . '" + str(root/'scripts/clock_policy.ps1') + "'; "
               "$c=Get-Content -Raw '" + str(root/'config/clocks.json') + "'|ConvertFrom-Json; "
               "Assert-SocDisplayClockHardware '" + str(root) + "' $c"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert (result.returncode == 0) == okay, result.stdout + result.stderr

def main():
    with tempfile.TemporaryDirectory(prefix='display30-') as name:
        root = Path(name)
        for item in ('scripts/clock_policy.ps1', 'config/clocks.json', 'config/display.json',
                     'config/timing_scope_baseline.json', 'rtl/soc/soc_top.v',
                     'rtl/video/pll_video.v', 'pds/soc.fdc'):
            dest = root/item
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/item, dest)
        display = json.loads((root/'config/display.json').read_text(encoding='utf-8-sig'))
        assert display['profile'] == '1080p30'
        assert display['pixel_hz'] == 74250000 and display['refresh_hz'] == 30
        assert display['width'] == 1920 and display['height'] == 1080
        check(root, True)
        path = root/'rtl/soc/soc_top.v'
        original = path.read_text()
        assert original.count('.PIXEL_DIVISOR(12)') == 1
        path.write_text(original.replace('.PIXEL_DIVISOR(12)', '.PIXEL_DIVISOR(6)'))
        check(root, False)
        path.write_text(original)
        path = root/'config/display.json'
        for field, bad in [('refresh_hz', 60), ('pixel_hz', 148500000),
                           ('pixel_divisor', 6), ('width', 1280)]:
            broken = dict(display)
            broken[field] = bad
            path.write_text(json.dumps(broken))
            check(root, False)
        path.write_text(json.dumps(display))
        path = root/'pds/soc.fdc'
        original = path.read_text()
        assert '13.468' in original
        path.write_text(original.replace('{13.468}', '{6.734}'))
        check(root, False)
    print('DISPLAY30_POLICY_PASS 1 positive 6 negative')

if __name__ == '__main__':
    main()
