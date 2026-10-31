"""Original three graphs on host scalar device oracle, exact baseline board CRCs."""
from pathlib import Path
import argparse, hashlib, io, json, re, subprocess, tarfile, uuid
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--assets',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest=a.assets/'manifest.json';data=json.loads(manifest.read_text());assert not data['synthetic_weights']
    includes=['linux/picture_new/upstream/adapter/runtime','linux/picture_new/upstream/linux/vision','linux/mac_accel','sw/bootloader']
    sources=['linux/picture_new/vision32_backend.c','linux/picture_new/vision32_layer.c','linux/picture_new/picture_new_bench.c',
             'linux/picture_new/upstream/adapter/runtime/xq_native_graph.c','sw/bootloader/crc32_fast.c','sim/picture_new_graph_mock.c']
    files=set(sources+['linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'])
    for directory in includes:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).glob('*.h'))
    hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}
    native='/var/tmp/opt60-picture-graphs-'+uuid.uuid4().hex
    flags='-std=c11 -O2 -Wall -Wextra -Werror -ffp-contract=off '+' '.join('-I'+native+'/'+n for n in includes)
    script='set -eu\nexport PATH=/usr/bin:/bin\n'
    script+=f"gcc {flags} "+' '.join(native+'/'+n for n in sources)+f' -Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl -lm -o {native}/bench\n'
    script+=f'mkdir {native}/assets; tar -xzf {native}/assets.tar.gz -C {native}/assets\n'
    for model in ['classifier','board','detector']:
        script+=f'{native}/bench {model} {native}/assets/{model}.xqm {native}/assets/{model}.f32 1 vision32 1\n'
    (out/'test.sh').write_text(script,newline='\n')
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w') as t:
        for n in files:t.add(ROOT/n,arcname=n,recursive=False)
        t.add(out/'test.sh',arcname='test.sh');t.add(a.assets/'timing-assets.tar.gz',arcname='assets.tar.gz')
    r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',f"set -eu; mkdir '{native}'; tar -xf - -C '{native}'; timeout --kill-after=5 300 sh '{native}/test.sh'"],input=payload.getvalue(),capture_output=True,timeout=330)
    (out/'test.log').write_bytes(r.stdout+r.stderr)
    body=(out/'test.log').read_text(errors='replace');assert r.returncode==0,body[-3500:]
    results={}
    for line in body.splitlines():
        if line.startswith('PICTURE_TIMING '):
            fields=dict(re.findall(r'(\w+)=([^\s]+)',line));results[fields['model']]=fields
    assert set(results)=={'board','detector','classifier'}
    for model,crc in [('classifier','805678c7'),('board','d830c1cd'),('detector','97265de4')]:assert results[model]['output_crc']==crc,(model,results[model])
    assert int(results['detector']['jobs'])<19444//10,'Require at least10x fewer submitted detector jobs'
    assert hashes=={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}
    record=dict(status='ORIGINAL_THREE_GRAPHS_SPATIAL_ORACLE_AND_JOB_REDUCTION_PASS_NOT_BOARD',results=results,
                inputs_sha256=hashes,assets_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                scope='Host device oracle, original full-size models and fixed input CRCs. Host time and zero mocked cycles are not FPGA latency.')
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(status=record['status'],jobs={k:v['jobs'] for k,v in results.items()})))
if __name__=='__main__':main()
