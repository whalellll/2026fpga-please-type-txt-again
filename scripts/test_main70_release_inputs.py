"""Exercise current release policy, real CRC captures, model and SD8 checks.

This is an offline subset test, never a complete release or physical approval.
"""
from pathlib import Path
import argparse,hashlib,json,math,statistics,tempfile
from verify_main70_release import efficiency,runtime,GUI,BIT
from coremark_crc_reference import CrcReference
from verify_board_release import parse_uart,validate_program_transcript
from compare_main70_models import compare

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];a.output.mkdir(parents=True,exist_ok=False)
    tests=[]
    for control,candidate in [(5.2,5.2),(5.2,5.3),(5.2,5.16)]:
        efficiency(control,candidate);tests.append('current-policy-positive')
    for control,candidate in [(5.2,5.149),(math.nan,5.2),(5.2,math.inf),(-1,5.2),(5.2,0)]:
        try:efficiency(control,candidate)
        except ValueError:tests.append('invalid-efficiency-rejected')
        else:raise AssertionError('Invalid efficiency accepted')
    sdpath=a.work/'kit-04/manifest.json'
    sd=runtime(root,dict(path=sdpath.relative_to(root).as_posix(),sha256=sha(sdpath)))
    tests.append('actual-sd8-dtb-rootfs-runtime-support-and18-loader-tests')
    pair=read(a.work/'coremark-abab-02/result.json');values={'control':[],'candidate':[]}
    tempfile.tempdir=str(a.output)
    with CrcReference(root,'G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe') as oracle:
        for batch in pair['batches']:
            p=Path(batch['coremark_result']);cm=read(p);uart=p.parent/'uart.log'
            assert sha(p)==batch['coremark_sha256'] and cm['status']=='PASS' and sha(uart)==cm['log_sha256']
            progpath=Path(batch['program_receipt']);program=read(progpath)
            programlog=progpath.with_suffix('.log')
            assert sha(progpath)==batch['program_sha256'] and sha(programlog)==program['program_log_sha256']
            validate_program_transcript(programlog.read_text(errors='replace'),program['assigned_bitstream_path'])
            text=uart.read_text(errors='replace');rows=parse_uart(text,batch['cpu_hz'],oracle)
            assert len(rows)==4 and all(x['iterations']==6000 and x['duration_seconds']>=10 for x in rows)
            role=batch['label'].split('-')[0];values[role].extend(x['coremark_per_mhz'] for x in rows[:3])
            tests.append('actual-four-crc-captures-'+batch['label'])
        # A corrupt captured CRC must fail even if its outer file hash is replaced.
        broken=text.replace('[0]crcfinal', '[0]badfinal',1)
        try:parse_uart(broken,70000000,oracle)
        except ValueError:tests.append('corrupt-uart-crc-rejected')
        else:raise AssertionError('Changed CRC capture accepted')
    means={k:statistics.mean(v) for k,v in values.items()};decrease=efficiency(means['control'],means['candidate'])
    report=compare(a.work/'model-comparison-01/control',a.work/'model-comparison-01/candidate')
    assert all(x['nonregression'] for x in report['metrics'].values());tests.append('all-recorded-parent60-model-comparison')
    result=dict(status='MAIN70_OFFLINE_RELEASE_INPUT_SUBSET_PASS_PHYSICAL_AND_FULL_RELEASE_PENDING',tests=tests,
                coremark_per_mhz=means,absolute_decrease=decrease,gui_elf_sha256=GUI,bitstream_sha256=BIT,formal_delivery=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])

if __name__=='__main__':main()
