"""Execute the actual kernel batch function with explicit IO/owner/time stubs."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--reuse-snapshot',action='store_true');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 driver=ROOT/'linux/mac_accel/kernel/pango_mac.c';uapi=ROOT/'linux/mac_accel/pango_mac_uapi.h';harness=ROOT/'sim/pikafish_batch_driver_harness.c'
 source=driver.read_text();start=source.index('struct pango_mac_batch_snapshot {');end=source.index('static long pango_mac_ioctl',start)
 actual=source[start:end];assert 'static int pango_mac_run_batch' in actual
 reuse=a.reuse_snapshot or 'snapshot=ctx->batch_snapshot;' in actual
 text=harness.read_text().replace('/* ACTUAL_KERNEL_BATCH_INSERT */',actual)
 target=out/'test.c';target.write_text(text)
 (out/'include/sys').mkdir(parents=True);(out/'include/sys/ioctl.h').write_text('/* No ioctl syscalls in this extracted-function harness. */\n')
 from workspace_paths import workspace_path,wsl_path
 env=dict(os.environ);prefix=['wsl.exe','-d','pikafish-verify','--','env','TMPDIR='+wsl_path(out)]
 direct_input='snapshot->input' not in actual
 coalesced='span_start' in actual
 commands=[('compile',[*prefix,'gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-DPANGO_TEST_REUSED_SNAPSHOT'] if reuse else []),*(['-DPANGO_TEST_INPUT_DIRECT'] if direct_input else []),*(['-DPANGO_TEST_COPYOUT_COALESCED'] if coalesced else []),'-I',wsl_path(out/'include'),'-I',wsl_path(uapi.parent),wsl_path(target),'-o',wsl_path(out/'test')]),('execute',prefix+[wsl_path(out/'test')])]
 for name,cmd in commands:
  r=subprocess.run(cmd,capture_output=True,env=env,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr)
  assert r.returncode==0,(name,(r.stdout+r.stderr).decode(errors='replace')[-3000:])
 assert b'ACTUAL_BATCH_DRIVER_' in (out/'execute.log').read_bytes()
 if reuse:assert b'NO_HOT_ALLOCATION_PASS' in (out/'execute.log').read_bytes()
 report=dict(status='ACTUAL_BATCH_DRIVER_TRANSACTION_STUB_PASS_NOT_KERNEL_OR_BOARD',scope='Actual batch function; mocked registers, DDR endpoint, locks and time. Not a kernel scheduler/physical DMA test.',sources_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (driver,uapi,harness)},logs_sha256={name:hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest() for name,_ in commands})
 report['reused_snapshot']=reuse
 report['direct_input_publish']=direct_input
 report['coalesced_copyout']=coalesced
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
if __name__=='__main__':main()
