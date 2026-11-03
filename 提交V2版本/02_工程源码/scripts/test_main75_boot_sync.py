"""Check exact GUI clock guards, timer ratio and strict SD boot receipts."""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,json,os,subprocess,sys
from workspace_paths import workspace_path,wsl_path
from board_boot_contract import validate
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    tmp=out/'tmp';tmp.mkdir();commands=[]
    native=wsl_path(out);temp=wsl_path(tmp)
    module_path=ROOT/'linux/opensbi/build_clock_candidate.py'
    spec=importlib.util.spec_from_file_location('clock_ratio',module_path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    cfg=json.loads((a.source_root/'config/clocks.json').read_text(encoding='utf-8-sig'))
    def candidate_ratio(profile):
        # This integer PLL uses fields that the generic ratio calculator does
        # not consume. Check the complete CPU75 profile before that calculation.
        assert profile['cpu_clock_source']=='dedicated675'
        assert profile['cpu_reference_hz']==27000000
        assert profile['cpu_output_divisor_eighths']==72
        return mod.clock_candidate_ratio(profile)
    assert candidate_ratio(cfg)==(33,50)
    mutations={'cpu_hz':60000000,'sys_hz':50000000,'cpu_divisor':26,'cpu_pll_vco_hz':1080000000,'cpu_reference_hz':125000000,'cpu_output_divisor_eighths':104}
    for key,value in mutations.items():
        bad=copy.deepcopy(cfg);bad[key]=value
        try:candidate_ratio(bad)
        except AssertionError:pass
        else:raise AssertionError('Clock mutation accepted: '+key)
    boot=b''.join(b'Loading '+n+b'\n' for n in [b'fw_jump.bin',b'Image',b'rootfs.cpio',b'soc.dtb',b'pikafish.pff',b'pikafish.atk'])
    boot+=b'MAIN75_SD_PAYLOADS_CRC_PASS cpu=75000000 sys=49500000 ratio=33/50\n/ # '
    validate(boot,'MAIN75',75000000)
    for bad in [boot.replace(b'33/50',b'33/40'),boot.replace(b'75000000',b'60000000'),boot.replace(b'/ # ',b''),boot+b'Kernel panic']:
        try:validate(bad,'MAIN75',75000000)
        except AssertionError:pass
        else:raise AssertionError('Bad boot receipt accepted')
    sources=[ROOT/'sim/test_xinyi_clock_contract.c',ROOT/'linux/xinyi_board/platform.c',ROOT/'linux/xinyi_board/platform.h',ROOT/'linux/xinyi_board/clock_contract.h',ROOT/'linux/xinyi_board/accelerator_idle.c',ROOT/'linux/xinyi_board/test_accelerator_idle.c',ROOT/'linux/opensbi/pg2l_timer_bridge.h',module_path,ROOT/'scripts/board_boot_contract.py']
    before={str(p):sha(p) for p in sources}
    def run(name,args,marker=None):
        cmd=['wsl.exe','-d','pikafish-verify','--','env','TMPDIR='+temp,'TMP='+temp,'TEMP='+temp,*args]
        p=subprocess.run(cmd,capture_output=True,timeout=180)
        (out/(name+'.log')).write_bytes(p.stdout+p.stderr)
        commands.append(dict(name=name,command=cmd,exit=p.returncode,log_sha256=sha(out/(name+'.log'))))
        assert p.returncode==0,(name,(p.stdout+p.stderr)[-2000:])
        if marker:assert marker in p.stdout,name
    for cpu,num,den in [(60000000,33,40),(70000000,99,140),(75000000,33,50)]:
        for target,cc,flags in [('host','gcc',[]),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',['-static','-march=rv32ima','-mabi=ilp32'])]:
            name=target+'-'+str(cpu);binary=native+'/'+name
            args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-pthread','-DXINYI_CPU_HZ='+str(cpu),'-DPG2L_TIME_NUMERATOR='+str(num),'-DPG2L_TIME_DENOMINATOR='+str(den),*flags]
            args+=['-I'+wsl_path(ROOT/p) for p in ['linux/xinyi_board','linux/xinyi','linux/vision','linux/picture_new','linux/mac_accel','sw/xiangqi','sw/bootloader','linux/opensbi']]
            args += [wsl_path(ROOT/'sim/test_xinyi_clock_contract.c'),wsl_path(ROOT/'linux/xinyi_board/platform.c'),'-Wl,--gc-sections','-o',binary]
            run(name+'-build',args)
            run(name+'-run',(['qemu-riscv32'] if target=='rv32' else [])+[binary],('XINYI_EXACT_CLOCK_PASS cpu='+str(cpu)).encode())
    for target,cc,extra in [('host','gcc',[]),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',['-static','-march=rv32ima','-mabi=ilp32'])]:
        binary=native+'/'+target+'-accelerator'
        run(target+'-accelerator-build',[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*extra,'-I'+wsl_path(ROOT/'linux/mac_accel'),wsl_path(ROOT/'linux/xinyi_board/test_accelerator_idle.c'),wsl_path(ROOT/'linux/xinyi_board/accelerator_idle.c'),'-o',binary])
        run(target+'-accelerator-run',(['qemu-riscv32'] if target=='rv32' else [])+[binary],b'batch_versions=10000,10001 unknown_rejected=4')
    assert all(sha(Path(p))==h for p,h in before.items())
    result=dict(status='MAIN75_GUI_EXACT_CLOCK_TIMER_RATIO_HOST_RV32_AND_BOOT_NEGATIVES_PASS_NOT_BOARD',sources_sha256=before,clock_mutations_rejected=len(mutations),boot_mutations_rejected=4,commands=commands)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])

if __name__=='__main__':main()
