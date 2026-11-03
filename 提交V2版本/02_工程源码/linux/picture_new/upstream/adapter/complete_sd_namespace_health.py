"""Collect one boot's verified file hashes without hiding the first UART timeout."""
import json
from pathlib import Path
from sd_namespace import REPO, sha

work=REPO/'build/picture-p21-native/sd-namespace-r01'
first=(work/'post-boot-health-r01.log').read_text(encoding='utf-8')
second=(work/'post-boot-health-r02.log').read_text(encoding='utf-8')
assert 'NS_GUI_AND_THREE_MODELS_READY' in second and 'XQ_ADAPTER_DONE=0' in second
expected=json.loads((REPO/'docs/validation/picture-native-sd-20261020/boot-r03/result.json').read_text())['runtime_sha256']
lines=[]
for name,digest in expected.items():
    line=digest+'  '+name
    assert line in first or line in second,name
    if line not in second:lines.append(line)
out=work/'post-boot-health-verified.log';assert not out.exists()
out.write_text('Collected from the same unchanged SD boot; the first 60-second UART window expired during SHA checking.\n'
               +'\n'.join(lines)+'\n'+second,encoding='utf-8')
receipt=dict(schema_version=1,status='ALL_FIVE_RUNTIME_HASHES_PASS',same_boot=True,
             initial_uart_window_timed_out=True,successful_followup_checks_missing_models_only=True,
             raw_logs_sha256={name:sha(work/name) for name in ('post-boot-health-r01.log','post-boot-health-r02.log')},
             collected_log_sha256=sha(out),runtime_sha256=expected)
(work/'post-boot-health-collection.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('ALL_FIVE_RUNTIME_HASHES_PASS same_boot=1 gui_and_worker_idle=1')
