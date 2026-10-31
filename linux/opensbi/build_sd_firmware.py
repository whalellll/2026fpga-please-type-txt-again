"""Build clock-matched OpenSBI for the normal SD chain. Run under WSL."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,signal,subprocess,sys
from build_clock_candidate import clock_candidate_ratio

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'scripts'))
from workspace_paths import workspace_path
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True)
    a=ap.parse_args();source=workspace_path(a.source_root);out=workspace_path(a.output)
    assert not out.exists();out.mkdir(parents=True)
    temporary=out/'tmp';temporary.mkdir()
    env=dict(os.environ,TMPDIR=str(temporary),TMP=str(temporary),TEMP=str(temporary))
    clock=source/'config/clocks.json';cfg=json.loads(clock.read_text())
    numerator,denominator=clock_candidate_ratio(cfg)
    assert cfg['cpu_hz']==70000000 and (numerator,denominator)==(99,140)
    archive=a.archive.resolve()
    assert sha(archive)=='ee5be2c582f9a837e9db88368220758e014dd694b566bb6c8efe1e50cfad0004'
    patch=source/'linux/opensbi/0001-pg2l-clock-config-timer-bridge.patch'
    header=source/'linux/opensbi/pg2l_timer_bridge.h'
    inputs={str(p):sha(p) for p in [clock,archive,patch,header,Path(__file__),PROJECT/'linux/opensbi/build_clock_candidate.py']}
    record=dict(status='BUILDING_NOT_BOARD',cpu_hz=cfg['cpu_hz'],sys_hz=cfg['sys_hz'],ratio=[numerator,denominator],inputs_sha256=inputs,commands=[],owner_pid=os.getpid())
    def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(name,cmd,cwd=None,timeout=300):
        item=dict(name=name,command=list(map(str,cmd)),cwd=str(cwd or out));record['commands'].append(item);save()
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.Popen(item['command'],cwd=cwd or out,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            try:code=p.wait(timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait();raise
        item.update(exit=code,log_sha256=sha(out/(name+'.log')));save()
        assert code==0,name
    save()
    try:
        run('extract',['tar','-xzf',archive,'-C',out])
        tree=out/'opensbi-1.3.1'
        run('patch',['patch','--batch','--fuzz=0','-p1','-i',patch],tree)
        shutil.copyfile(header,tree/'lib/sbi/pg2l_timer_bridge_impl.h')
        wrapper=f'#define PG2L_TIME_NUMERATOR {numerator}\n#define PG2L_TIME_DENOMINATOR {denominator}\n#include "pg2l_timer_bridge_impl.h"\n'
        (tree/'lib/sbi/pg2l_timer_bridge.h').write_text(wrapper)
        (out/'clock_ratio.h').write_text(wrapper)
        run('compiler',['riscv64-linux-gnu-gcc','-v'])
        run('make',['make','-j2','PLATFORM=generic','FW_TEXT_START=0x18000000','FW_JUMP_ADDR=0x00400000','FW_JUMP_FDT_ADDR=0x1a000000','CROSS_COMPILE=riscv64-linux-gnu-','PLATFORM_RISCV_XLEN=32','PLATFORM_RISCV_ISA=rv32ima_zicsr_zifencei','PLATFORM_RISCV_ABI=ilp32'],tree,900)
        for name in ['fw_jump.bin','fw_jump.elf']:
            shutil.copyfile(tree/'build/platform/generic/firmware'/name,out/name)
        assert 200000<(out/'fw_jump.bin').stat().st_size<327680
        elf=(out/'fw_jump.elf').read_bytes();assert elf[:6]==b'\x7fELF\x01\x01'
        assert all(sha(Path(n))==h for n,h in inputs.items())
        record.update(status='CPU70_SD_OPENSBI_99_140_BUILD_PASS_NOT_BOARD',outputs_sha256={n:sha(out/n) for n in ['fw_jump.bin','fw_jump.elf','clock_ratio.h']},completed_utc=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        record.update(status='CPU70_SD_OPENSBI_BUILD_FAILED_PRESERVED',error=str(error));raise
    finally:save()
    print(record['status'])

if __name__=='__main__':main()
