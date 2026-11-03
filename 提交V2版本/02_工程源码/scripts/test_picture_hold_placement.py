"""Keep exact physical placement review separate from unchanged CDC bounds."""
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('cpu_cdc_audit', ROOT / 'pds/audit_cpu_sys_cdc_ads.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
FDC = (ROOT / 'pds/soc.fdc').read_text(encoding='utf-8')
LEGACY = re.sub(r'(?ms)^# PICTURE_CPU_ROB_HOLD_PLACEMENT v3\r?\n.*?^# END_PICTURE_CPU_ROB_HOLD_PLACEMENT\s*$', '', FDC)


class HoldPlacementTest(unittest.TestCase):
    def test_python_legacy_and_exact_new_count(self):
        self.assertEqual(AUDIT.reviewed_physical_placement_count(LEGACY), 0)
        self.assertEqual(AUDIT.reviewed_physical_placement_count(FDC), 1)
        self.assertEqual(AUDIT.EXPECTED_CONSTRAINTS, 1171)

    def test_python_reject_incomplete_relocated_or_unmarked_binding(self):
        for changed in (FDC.replace('CLMA_189_402', 'CLMA_225_396'),
                        FDC.replace('PICTURE_CPU_ROB_HOLD_PLACEMENT v3', 'PICTURE_CPU_ROB_HOLD_PLACEMENT v0'),
                        FDC.replace(':FF1}', ':FF3}')):
            with self.assertRaises(AUDIT.AuditError):
                AUDIT.reviewed_physical_placement_count(changed)

    def test_powershell_same_count_and_rejections(self):
        with tempfile.TemporaryDirectory(prefix='hold-placement-policy-') as folder:
            scratch = Path(folder)
            (scratch / 'pds').mkdir()
            script = scratch / 'check.ps1'
            script.write_text('''param([string]$Source,[string]$Fixture)
$ErrorActionPreference='Stop'
. (Join-Path $Source 'scripts/build_snapshot.ps1')
Write-Output (Get-FpgaConstraintCount $Fixture)
''', encoding='utf-8')
            for text, expected in ((LEGACY, 1171), (FDC, 1172),
                                   (FDC.replace(':FF1}', ':FF3}'), None)):
                (scratch / 'pds/soc.fdc').write_text(text, encoding='utf-8')
                run = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                      '-File', str(script), '-Source', str(ROOT), '-Fixture', str(scratch)],
                                     capture_output=True, text=True, timeout=30)
                if expected is None:
                    self.assertNotEqual(run.returncode, 0)
                else:
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(run.stdout.strip(), str(expected))

    def test_native_packed_name_and_location_are_exact(self):
        # Observed in the full b2ffa03d dev_map, rather than the uncombined
        # explicit primitives of the small probe. Neither name aliases nor
        # wrong/missing/duplicate placement records are accepted.
        line = ('def_inst_site {u_cpu/u_cpu_wrapper/u_cpu/core/'
                'backend_io_memoryStoreData_REG[25]/opit_0_L6QL5Q} CLMA_189_402 FF1')
        with tempfile.TemporaryDirectory(prefix='packed-hold-policy-') as folder:
            scratch = Path(folder)
            (scratch / 'pds').mkdir()
            (scratch / 'pds/soc.fdc').write_text(FDC, encoding='utf-8')
            script = scratch / 'check.ps1'
            script.write_text('''param([string]$Source,[string]$Fixture)
$ErrorActionPreference='Stop'
. (Join-Path $Source 'scripts/build_snapshot.ps1')
Assert-FpgaPictureHoldPcf $Fixture (Join-Path $Fixture 'actual.pcf')
''', encoding='utf-8')
            for text, accepted in ((line, True),
                                   (line.replace('_L6QL5Q', ''), False),
                                   (line.replace('189_402', '225_396'), False),
                                   (line.replace('FF1', 'FF2'), False),
                                   (line + '\n' + line, False), ('', False)):
                (scratch / 'actual.pcf').write_text(text + '\n', encoding='utf-8')
                run = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                      '-File', str(script), '-Source', str(ROOT), '-Fixture', str(scratch)],
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode == 0, accepted, run.stderr)


if __name__ == '__main__':
    unittest.main()
