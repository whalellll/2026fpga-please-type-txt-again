"""Verify the accepted CPU80 package independently of legacy V2.1 run IDs."""
from pathlib import Path, PurePosixPath
import argparse, gzip, hashlib, json, math, statistics, tarfile, xml.etree.ElementTree as ET, zlib
from coremark_crc_reference import CrcReference
from verify_board_release import parse_uart, validate_program_transcript

RUN='f79443a2e020498c853ce868cde9b187'
CPU='fefd93052c4974c5a45fcebb7a34cc3d44f9a8d9'
RTL='95a5a197b07719948c36941b3a64308183704297d3cb4702347dc985ad2708f0'
BIT='b075be18325630d89de8b168baf5caec471395991ec69b61e3e77bca0d7ad88e'
ARCHIVE='ab42c49867d165b1ebada252f1304c81b043b96214306a4e99c91d66d447131e'
BASE='docs/validation/cpu80-20261020-csrcount-retry'
def need(ok,why):
    if not ok: raise ValueError(why)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def safe(root,name):
    need(isinstance(name,str) and name and '\\' not in name and ':' not in name and '..' not in PurePosixPath(name).parts and not name.startswith('/'),'Unsafe package path')
    p=root/name
    need(p.is_file() and not p.is_symlink(),'Missing/linked package file: '+name)
    return p
def timing(xml):
    tables={t.get('id'):[[d.text for d in row.findall('data')] for row in t.findall('row')] for t in ET.fromstring(xml).findall('table')}
    count=0
    for corner in ['slow','fast']:
        for kind in ['setup','hold','recovery','removal','mpw']:
            rows=tables['report_timing_'+corner+'_'+kind];need(bool(rows),'Empty timing table')
            off=1 if kind=='mpw' else 2
            for r in rows:
                need(len(r)==off+4 and float(r[off])>=0 and float(r[off+1])==0 and int(r[off+2])==0 and int(r[off+3])>0,'Negative slack or failing timing endpoint')
                count+=1
        skew=tables['report_timing_'+corner+'_path_max_skew']
        need(len(skew)==10 and all(float(r[1])>=0 for r in skew),'Max-skew failure')
    need(count==116,'Incomplete final corner coverage')
    checks={r[0]:int(r[1]) for r in tables['check_timing_summary']}
    need(all(checks[k]==0 for k in ['no_clock','unexpandable_clocks','loops','latchs']),'Timing coverage/control failure')
    need(checks['no_input_delay']==61 and checks['no_output_delay']==128,'I/O coverage changed without acceptance')
    return count
def validate(root,host_gcc,inventory=True):
    root=Path(root).resolve();m=read(root/'CPU80_DELIVERY.json')
    need(m['status']=='CPU80_BOARD_VERIFIED_DELIVERY' and m['run_id']==RUN and m['cpu_implementation_commit']==CPU,'Wrong delivery identity/status')
    if inventory:
        for n,d in m['files_sha256'].items():need(sha(safe(root,n))==d,'Package hash differs: '+n)
    s=read(root/'artifacts/build_snapshot.json');e=read(root/'artifacts/build_evidence.json')
    need(s['run_id']==e['run_id']==RUN and len(s['inputs'])==455,'Frozen run/input inventory differs')
    for n,d in s['inputs'].items():need(sha(safe(root,n))==d,'Frozen implementation changed: '+n)
    need(e['timing']=='All Constraints Met' and e['timing_scope_verified'] is True and e['max_skew_verified'] is True,'Native STA/scope failed')
    need(sha(root/'rtl/cpu/CoreTop.sv')==RTL and sha(root/'artifacts/soc_top.sbit')==BIT,'Wrong accepted CPU/bitstream')
    need(sha(safe(root,'pds/bootrom.hex'))==sha(root/'artifacts/bootrom.hex'),'Simulation/PDS ROM differs from accepted firmware')
    src=read(root/'rtl/cpu/source.json');need(src['source_reference_commit']==CPU and src['sha256']==RTL,'CPU source pairing differs')
    need(sha(root/'artifacts/build_snapshot.json')==e['input_snapshot_sha256'],'Snapshot hash differs')
    for n in ['artifacts/final_timing_report.txt','artifacts/final_timing_xml.xml','artifacts/bootloader.bin','artifacts/bootloader.elf','artifacts/bootrom.hex']:
        need(sha(safe(root,n))==e['outputs'][n],'Native output differs: '+n)
    timing((root/'artifacts/final_timing_xml.xml').read_bytes())
    need('Design Summary : All Constraints Met.' in (root/'artifacts/final_timing_report.txt').read_text(),'Native RTR summary failed')
    correctness=root/'docs/validation/cpu80-20261020-csrcount/correctness'
    cr=read(correctness/'result.json')
    need(cr['cpu_commit']==CPU and cr['cpu_rtl_sha256']==RTL and cr['cpu_tests']==121 and cr['cpu_suites']==42,'Full CPU correctness identity differs')
    for n,d in cr['files_sha256'].items():need(sha(safe(correctness,n))==d,'Correctness evidence changed: '+n)
    full=read(correctness/'full.json');reg=read(correctness/'full-entry-csrcount-pre-pnr.json')
    need(full['status']=='PASS' and reg['status']=='FULL_ENTRY_PASS' and reg['firmware_bytes_identical'] is True,'CPU/SoC full regression failed')
    need(hashlib.sha256(gzip.decompress((correctness/'full.log.gz').read_bytes())).hexdigest()==full['logs']['full.log'],'Full CPU log changed')
    reglog=gzip.decompress((correctness/'full-entry-csrcount-pre-pnr.log.gz').read_bytes())
    need(hashlib.sha256(reglog).hexdigest()==reg['log_sha256'] and b'SOC_ALL_TESTS_PASS' in reglog,'Full SoC log changed')
    board=root/BASE/'board';b=read(board/'result.json')
    need(b['run_id']==RUN and b['bitstream_sha256']==BIT and b['status']=='BOARD_FUNCTIONAL_PERFORMANCE_PASS_HDMI_CONFIRMED','Current board acceptance missing')
    need(b['hdmi_visual']=='USER_CONFIRMED' and b['performance_nonregression_gate']=='PASS_SAME_SESSION_COREMARK_NNUE_DENSE','HDMI/performance gate missing')
    need(read(board/'hdmi-confirmation.json')['status']=='USER_CONFIRMED','Missing actual user HDMI record')
    for n,d in b['files_sha256'].items():need(sha(safe(board,n))==d,'Board evidence hash differs: '+n)
    pooled=read(board/'coremark-ab-pooled.json');all_runs={}
    with CrcReference(root,host_gcc) as oracle:
        for hz,names in [(75000000,['baseline75-program-coremark','repeat/repeat75']),(80000000,['program80','repeat/repeat80'])]:
            values=[]
            for name in names:
                q=board/name;cm=read(q/'coremark/result.json');program=read(q/'program.json')
                need(cm['status']=='PASS' and cm['board_acceptance'] is True and program['status']=='PASS','CoreMark/program gate failed')
                expected=BIT if hz==80000000 else '2eb59589182005d2cfd059c8be12bc9b6a83ab10ac1990e4f6b91095d6e34274'
                need(cm['bitstream']['sha256']==program['bitstream_sha256']==expected,'Measured bitstream differs')
                need(cm['firmware']['sha256']==sha(root/'artifacts/bootloader.bin'),'Measured firmware differs')
                validate_program_transcript((q/'program.log').read_text(errors='replace'),program['assigned_bitstream_path'])
                need(sha(q/'coremark/uart.log')==cm['log_sha256'],'CoreMark UART changed')
                parsed=parse_uart((q/'coremark/uart.log').read_text(errors='replace'),hz,oracle)
                values+=parsed[:3]
            need(len(values)==6,'All six performance samples required')
            all_runs[hz]=values
            for key in ['iterations_per_second','coremark_per_mhz']:
                side='candidate80' if hz==80000000 else 'baseline75';stored=pooled['comparisons'][key][side]
                need(all(math.isclose(x[key],y,rel_tol=1e-12) for x,y in zip(values,stored['all_values'])) and len(stored['all_values'])==6,'Pooled samples changed')
                need(math.isclose(statistics.mean(v[key] for v in values),stored['mean'],rel_tol=1e-12),'Pooled arithmetic differs')
    need(all(statistics.mean(v[k] for v in all_runs[80000000])>=statistics.mean(v[k] for v in all_runs[75000000]) for k in ['iterations_per_second','coremark_per_mhz']),'Observed CoreMark regression')
    model=read(board/'model-check.json');base=read(board/'baseline75.json')
    need(model['run_id']==RUN and model['functional']['status']==model['nnue']['correctness_status']=='PASS','Official model/function failed')
    n=(board/'nnue80.uart').read_text(errors='replace').replace('\r','')
    for marker in model['nnue']['required_markers']:need(marker in n,'Official model raw marker missing: '+marker)
    for phase in ['cold','warm']:
        actual=model['nnue']['phases'][phase]
        need(actual['samples']==40 and actual['mean_us']<=base['phases'][phase]['mean_us'],'Observed official NNUE regression')
    for v in b['dense_mac_comparison'].values():need(v['candidate80_mean_us']<=v['baseline75_mean_us'],'Observed dense MAC regression')
    final_state=(board/'repeat/post-repeat-final-state80.uart').read_text(errors='replace')
    for marker in ['0x04C4B400','0x02F34F60','engine=ready nodes=0','mode=display-only']:
        need(marker in final_state,'Final CPU80 restored state missing')
    restore=read(board/'repeat/restore80-program.json')
    need(restore['status']=='PASS' and restore['pds_snapshot_run_id']==RUN and restore['bitstream_sha256']==BIT,'Final restoration differs')
    need('CPU80_H128_OFF_TWO_REGISTERS_PASS' in (board/'h128-off.uart').read_text(),'H128 retirement not verified')
    archive=root/'artifacts/cpu80_candidate_20261020/cpu-source-fefd9305.tar.gz'
    need(sha(archive)==ARCHIVE,'Paired CPU source archive changed')
    with tarfile.open(archive,'r:gz') as t:
        generated=[v for v in t.getmembers() if v.name.endswith('cpu/generated/core/CoreTop.sv')]
        need(len(generated)==1 and hashlib.sha256(t.extractfile(generated[0]).read()).hexdigest()==RTL,'CPU archive/generated RTL pairing differs')
    kit=root/'artifacts/cpu80_candidate_20261019/ram-boot80'
    for name,digest in read(kit/'selected-files.json')['files_sha256'].items():need(sha(safe(kit,name))==digest,'Matched RAM kit changed')
    for item in m['sd_readonly_payloads']:
        data=safe(root,item['path']).read_bytes()
        need(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'] and (zlib.crc32(data)&0xffffffff)==item['crc32'],'SD runtime payload differs')
    return dict(status='CPU80_DELIVERY_EVIDENCE_PASS',run_id=RUN,cpu_implementation_commit=CPU,rtl_sha256=RTL,bitstream_sha256=BIT,sta_rows=116,coremark_per_frequency='6 performance + 2 validation',hdmi='USER_CONFIRMED')

def check_zip(path):
    from zipfile import ZipFile
    with ZipFile(path) as z:
        names=z.namelist();need(len(names)==len(set(names)),'Duplicate ZIP entries')
        for n in names:
            need(n.startswith('SOC/') and ':' not in n and '\\' not in n and '..' not in PurePosixPath(n).parts,'Unsafe ZIP entry')
        m=json.loads(z.read('SOC/CPU80_DELIVERY.json'))
        need(set(names)=={'SOC/'+n for n in m['files_sha256']}|{'SOC/CPU80_DELIVERY.json'},'ZIP inventory differs')
        for n,d in m['files_sha256'].items():need(hashlib.sha256(z.read('SOC/'+n)).hexdigest()==d,'ZIP content differs: '+n)
    return m

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path);ap.add_argument('--zip',type=Path);ap.add_argument('--extract',type=Path);ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe');a=ap.parse_args()
    if a.zip:
        check_zip(a.zip)
        if a.extract:
            from zipfile import ZipFile
            need(not a.extract.exists(),'Use a new extraction directory')
            a.extract.mkdir(parents=True)
            with ZipFile(a.zip) as z:z.extractall(a.extract)
            a.root=a.extract/'SOC'
    need(a.root is not None,'Provide --root or --zip plus --extract')
    print(json.dumps(validate(a.root,a.host_gcc),indent=2))
