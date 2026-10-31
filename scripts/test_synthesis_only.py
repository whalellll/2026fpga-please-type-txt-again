"""Check the synthesis-only control-flow contract; native ADS is separate."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
source = (root / 'scripts/build_fpga.ps1').read_text(encoding='utf-8-sig')
assert '[switch]$SynthesisOnly' in source
assert 'if ($SynthesisOnly -and ($FinalizeCompletedBuild -or $CheckSdStorageOnly -or $RebuildHdmiAssets))' in source
pre = source.index('Write-Output "SOC_ADS_PREFLIGHT_PASS')
guard = source.index('if ($SynthesisOnly) {', pre)
stop = source.index('return', guard)
post = source.index("# Keep separate native histories", pre)
reservation = source.index('Register-PnrAttempt', post)
assert pre < guard < stop < post < reservation
assert "status = 'SYNTHESIS_ONLY_PASS_NOT_TIMING_OR_BOARD_ACCEPTANCE'" in source[guard:post]
assert 'pnr_started = $false' in source[guard:post]
assert '$pdsSucceeded = $true' in source[guard:stop]
for conflicting in ['FinalizeCompletedBuild', 'CheckSdStorageOnly', 'RebuildHdmiAssets']:
    run = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', str(root / 'scripts/build_fpga.ps1'), '-SynthesisOnly', '-'+conflicting],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert run.returncode != 0, conflicting
    assert b'SynthesisOnly cannot be combined' in run.stdout, (conflicting, run.stdout)
print('SYNTHESIS_ONLY_CONTROL_FLOW_PASS conflict_cases=3 native_ADS_not_implied=true')
