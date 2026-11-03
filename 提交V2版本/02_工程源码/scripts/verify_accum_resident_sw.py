"""Actual driver/runtime on RV32 and sanitizers, including legacy and eviction paths."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--driver-result',type=Path,required=True);p.add_argument('--rtl-result',type=Path,required=True);a=p.parse_args();o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False);(o/'tmp').mkdir()
sources=['linux/mac_accel/kernel/pango_mac.c','linux/mac_accel/pango_mac_uapi.h','linux/pikafish/pango_mac_uapi.h','linux/pikafish/pikafish_mac_runtime.cpp','linux/pikafish/pikafish_mac_runtime.h','sim/pikafish_batch_driver_harness.c','sim/test_pikafish_batch_runtime.cpp'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();bound={n:sha(R/n) for n in sources}
assert (R/sources[1]).read_bytes()==(R/sources[2]).read_bytes()
driver=workspace_path(a.driver_result).parent/'test.c';d=json.loads((driver.parent/'result.json').read_text());assert 'PASS' in d['status']
for n,h in d['sources_sha256'].items():assert sha(R/n)==h
logs={}
for arch in ['native-sanitize','rv32']:
 native=arch.startswith('native');cc='gcc' if native else '/opt/toolchain/bin/riscv32-linux-musl-gcc';cxx='g++' if native else '/opt/toolchain/bin/riscv32-linux-musl-g++'
 extra='-g -fsanitize=address,undefined -fno-omit-frame-pointer' if native else '-static'
 script=f'''set -eu
export TMPDIR='{wsl_path(o/'tmp')}' TMP='{wsl_path(o/'tmp')}' TEMP='{wsl_path(o/'tmp')}'
{cc} -std=c11 -O2 -Wall -Wextra -Werror {extra} -DPANGO_TEST_REUSED_SNAPSHOT -DPANGO_TEST_INPUT_DIRECT -DPANGO_TEST_COPYOUT_COALESCED -I'{wsl_path(driver.parent/'include')}' -I'{wsl_path(R/'linux/mac_accel')}' '{wsl_path(driver)}' -o '{wsl_path(o/(arch+'-driver'))}'
{cxx} -std=c++17 -O2 -pthread -Wall -Wextra -Werror {extra} -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -iquote '{wsl_path(R/'linux/pikafish')}' '{wsl_path(R/'sim/test_pikafish_batch_runtime.cpp')}' '{wsl_path(R/'linux/pikafish/pikafish_mac_runtime.cpp')}' '{wsl_path(R/'linux/pikafish/pikafish_stagea_accel.cpp')}' -Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl -o '{wsl_path(o/(arch+'-runtime'))}'
'''
 runner='' if native else 'qemu-riscv32 '
 script+=runner+"'"+wsl_path(o/(arch+'-driver'))+"'\n"
 for env in ['', 'TEST_OLD_COPYOUT_DRIVER=1 ', 'TEST_SINGLE_GATHER=1 ', 'TEST_RESIDENT_DRIVER=1 PIKAFISH_ACCUM_RESIDENT=1 ', 'TEST_RESIDENT_DRIVER=1 PIKAFISH_ACCUM_RESIDENT=0 ']:script+=env+runner+"'"+wsl_path(o/(arch+'-runtime'))+"'\n"
 (o/(arch+'.sh')).write_text(script,newline='\n')
 q=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh',wsl_path(o/(arch+'.sh'))],capture_output=True,timeout=240);(o/(arch+'.log')).write_bytes(q.stdout+q.stderr)
 assert q.returncode==0,(arch,(q.stdout+q.stderr)[-3000:])
 for marker in [b'ACCUM_RESIDENT_DRIVER_HIT_BYTES_ZERO_STALE_AND_FOREIGN_SHADOW_RECOVERY_CONFLICT_ERROR_AND_WRAP_PASS',b'ACCUM_RESIDENT_RUNTIME_HIT_EVICTION_SHADOW_SNAPSHOT_POINTER_CHANGE_CLOBBER_AND_MAPPING_PASS']:assert marker in q.stdout,(arch,marker)
 logs[arch]=sha(o/(arch+'.log'))
assert all(sha(R/n)==h for n,h in bound.items())
sim=workspace_path(a.rtl_result).parent;s=json.loads((sim/'result.json').read_text())
for n,h in s['source_sha256'].items():assert sha(R/n)==h,n
assert sha(sim/'simulation.log')==s['log_sha256']
text=(sim/'simulation.log').read_bytes();m=re.search(rb'ACCUM_RESIDENT_CYCLES external=(\d+) resident=(\d+) external_base_words=1024 resident_base_words=0',text);assert m
report=dict(status='ACCUM_RESIDENT_ACTUAL_DRIVER_RUNTIME_RV32_ASAN_UBSAN_OLD_DEVICE_AND_STALE_RECOVERY_PASS_NOT_BOARD',sources_sha256=bound,logs_sha256=logs,rtl_external_cycles=int(m[1]),rtl_resident_cycles=int(m[2]),rtl_base_read_bytes_before=4096,rtl_base_read_bytes_after=0,additional_fpga_context_ram_bytes=0,board_tested=False)
(o/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
