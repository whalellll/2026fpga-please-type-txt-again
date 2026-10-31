"""Verify paired Chisel/RTL, complete CPU regression and same-ROM cycle evidence."""
from pathlib import Path,PurePosixPath
import gzip,hashlib,json,re,tarfile

BASE='fefd93052c4974c5a45fcebb7a34cc3d44f9a8d9'
CPU='05c7ef96a8144edf7488efd1359d0855d055f501'
RTL='e8ae28118b91cd52ce4876a36f7d28efdc646979d960d48e87bc36ced35a88db'
BASE_RTL='95a5a197b07719948c36941b3a64308183704297d3cb4702347dc985ad2708f0'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def validate_cpu(path):
    path=Path(path).resolve();folder=path.parent;contract=read(path)
    assert contract['status']=='GUI1080_MUL_CPU_CORRECTNESS_PAIRED_SOURCE_PASS_NOT_STA_OR_BOARD'
    assert (contract['cpu_commit'],contract['rtl_sha256'],contract['base_cpu'])==(CPU,RTL,BASE)
    for name,h in contract['files_sha256'].items():
        p=PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts and '\\' not in name
        assert sha(folder/name)==h,name
    with tarfile.open(folder/contract['archive'],'r:gz') as archive:
        assert archive.pax_headers.get('comment')==CPU,'CPU archive commit differs'
        files={}
        for entry in archive.getmembers():
            name=PurePosixPath(entry.name)
            assert not name.is_absolute() and '..' not in name.parts
            if entry.isdir():continue
            assert entry.isfile() and entry.name.startswith('src/')
            files[entry.name[4:]]=archive.extractfile(entry).read()
    generated=json.loads(files['cpu/generated/manifest.json'])
    assert generated['schema_version']==2
    for section in ['source_files','outputs']:
        for name,h in generated[section].items():assert digest(files['cpu/'+name])==h,name
    assert digest(files['cpu/generated/core/CoreTop.sv'])==RTL
    configs={mode:json.loads(files['cpu/generated/'+mode+'/emit-config.json']) for mode in ['core','sim']}
    for mode,c in configs.items():
        assert c['supervisor'] is True and c['isa']=='rv32ima_zicsr_zifencei'
        assert c['architecture']==dict(aluEntries=4,memEntries=2,fallbackSets=64,fallbackHash=True,rasDepth=2)
        assert c['cache']==dict(lineBytes=32,l1Sets=128,iWays=2,dWays=2,l2Sets=512,l2Ways=1)
        assert c['mode']==dict(synthesis=mode=='core',socProbes=mode=='sim')
    sources={n:digest(data) for n,data in files.items() if n.endswith('.scala') and n.startswith(('cpu/src/main/','cpu/src/test/'))}
    for phase in ['baseline','focus','full']:
        r=read(folder/('cpu-'+phase+'.json'));assert r['status']=='PASS'
        expected=dict(sources)
        if phase=='baseline':expected['cpu/src/main/scala/e91c/exec/Mul.scala']=digest((folder/'baseline-Mul.scala').read_bytes())
        assert r['source_sha256']==expected,phase
        log=gzip.decompress((folder/('cpu-'+phase+'.log.gz')).read_bytes())
        assert digest(log)==r['logs']['cpu-'+phase+'.log'] and b'All tests passed.' in log
        tests=int(re.findall(rb'Total number of tests run: (\d+)',log)[0]);assert tests==r['tests']
        if phase=='full':
            assert tests==123 and re.search(rb'Suites: completed 43, aborted 0',log)
            assert b'Tests: succeeded 123, failed 0, canceled 0, ignored 0, pending 0' in log
        elif phase=='baseline':assert tests==2
    generation=read(folder/'cpu-generate.json')
    assert generation['status']=='PAIRED_GENERATION_PASS_NOT_STA_OR_BOARD' and generation['rtl_sha256']==RTL and generation['source_sha256']==sources
    for name,h in generation['logs'].items():assert digest(gzip.decompress((folder/(name+'.gz')).read_bytes()))==h,name
    original=(folder/'baseline-Mul.scala').read_bytes()
    assert digest(original)=='4f37e9d24c79667a0784b5de6656449be75659f631e62a2d8cbcc3fe0e07bfe4'
    assert files['cpu/src/test/scala/e91c/MulGui1080Reference.scala']==original.replace(b'class Mul extends Module',b'class MulGui1080Reference extends Module')
    modules=lambda data:{m[1]:m[0] for m in re.finditer(r'(?ms)^module\s+(\w+)\b.*?^endmodule',data.decode().replace('\r\n','\n'))}
    for mode,count in [('core',64),('sim',62)]:
        old=gzip.decompress((folder/('baseline-'+mode+'-CoreTop.sv.gz')).read_bytes())
        if mode=='core':assert digest(old)==BASE_RTL
        a,b=modules(old),modules(files['cpu/generated/'+mode+'/CoreTop.sv'])
        assert a.keys()==b.keys() and len(a)==count and [n for n in a if a[n]!=b[n]]==['Mul']
    cycles=read(folder/'coremark-cycles.json')
    assert cycles['status']=='GUI1080_SAME_ROM_BOTH_SEEDS_EXACT_CYCLES_CRC_PASS_NOT_BOARD_SCORE'
    a,b=cycles['cases']['control'],cycles['cases']['candidate']
    assert a['rtl_sha256']==BASE_RTL and b['rtl_sha256']==RTL and a['modes']==b['modes']
    skip={'rtl/cpu/CoreTop.sv','rtl/cpu/source.json'}
    assert {n:h for n,h in a['inputs_sha256'].items() if n not in skip}=={n:h for n,h in b['inputs_sha256'].items() if n not in skip}
    for side,entry in [('control',a),('candidate',b)]:
        assert digest(gzip.decompress((folder/('coremark-cycles-'+side+'.log.gz')).read_bytes()))==entry['log_sha256']
        p=folder/('coremark-'+side+'.evidence.json');assert sha(p)==entry['evidence_sha256']
        proof=read(p);assert len(proof['cases'])==2
        for item in proof['cases']:
            d=item['result'];assert d['status']=='PASS' and d['iterations']==10 and d['production_port_rejected_short_run'] is True
            assert entry['modes'][d['seed_mode']]==dict(rom_sha256=item['rom_sha256'],crc=d['crc'],measured_ticks=d['measured_ticks'],total_cpu_cycles=d['total_cpu_cycles'])
    return dict(status='GUI1080_CPU_123_TESTS_43_SUITES_PAIRED_ONLY_MUL_SAME_ROM_CYCLES_PASS_NOT_BOARD',cpu_commit=CPU,rtl_sha256=RTL,contract_sha256=sha(path),archive_sha256=sha(folder/contract['archive']))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--contract',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(validate_cpu(a.contract)))
