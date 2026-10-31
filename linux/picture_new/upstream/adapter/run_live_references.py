"""Run three explicit PC references on one captured input; never send results to GUI."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib

sys.dont_write_bytecode=True
REPO=Path(__file__).resolve().parents[2]
LIVE=REPO/'build/picture-p21-native/live-sd-r01'
GOLDEN=REPO/'artifacts/vision-model-20261020/golden'
HOST=REPO/'build/picture-p21-native/host-r04'

def run_one(name,args):
    with (LIVE/(name+'.log')).open('x') as log:
        result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=1800,env=os.environ.copy())
    return name,result.returncode

def main():
    raw=(LIVE/'frame.rgb565').read_bytes()
    request=(LIVE/'request.txt').read_text().split()
    assert len(raw)==1843200 and len(request)==5 and request[0]=='XQ_MODEL_REQUEST_V1'
    assert request[4]=='rv32-driver-quantized-mac' and zlib.crc32(raw)==int(request[3],16)
    if sys.argv[1:]==['--summarize-existing']:
        summarize(raw,dict.fromkeys(('pc-fp32','pc-quantized-mac','cpu-int32-reference')),True)
        return
    assert not sys.argv[1:]
    for name in ('pc-fp32.json','pc-quantized-mac.json','cpu-int32-reference.packet','cpu-int32-reference.request','pc-references.json'):
        assert not (LIVE/name).exists(),name
    request[4]='cpu-int32-reference'
    (LIVE/'cpu-int32-reference.request').write_text(' '.join(request)+'\n')
    subprocess.run(['sha256sum','--status','-c',str(HOST/'source-before.sha256')],check=True,timeout=30)
    jobs=[]
    for backend in ('fp32','quantized-mac'):
        jobs.append(('pc-'+backend,[sys.executable,str(GOLDEN/'recognize.py'),
           '--input',str(LIVE/'frame.rgb565'),'--output',str(LIVE/('pc-'+backend+'.json')),
           '--backend',backend,'--width','1280','--height','720','--byte-order','little','--stride-bytes','2560']))
    jobs.append(('cpu-int32-reference',[str(HOST/'xq-native-worker'),'--cpu-reference',
                 '--models',str(REPO/'build/picture-p21-native/model-r02'),
                 '--request',str(LIVE/'cpu-int32-reference.request'),'--input',str(LIVE/'frame.rgb565'),
                 '--output',str(LIVE/'cpu-int32-reference.packet')]))
    exits={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(run_one,name,args) for name,args in jobs]
        for future in concurrent.futures.as_completed(futures):
            name,code=future.result();exits[name]=code
            print(json.dumps(dict(reference=name,exit_code=code)),flush=True)
    summarize(raw,exits,False)

def summarize(raw,exits,existing):
    assert not (LIVE/'pc-references.json').exists()
    summary=dict(input_sha256=hashlib.sha256(raw).hexdigest(),input_crc32=f'{zlib.crc32(raw):08x}',
                 exits=exits,summarized_existing_outputs=existing,
                 device_inference=False,gui_results_sent=False,backends={})
    for name in ('pc-fp32','pc-quantized-mac'):
        assert exits[name] in (0,None)
        result=json.loads((LIVE/(name+'.json')).read_text())
        summary['backends'][name]=dict(status=result['status'],
            strict_usable=result.get('can_use_as_candidate') is True,
            piece_count=len(result.get('pieces',[])),issues=result.get('issues',[]),
            model_count=len(result.get('models',{})),production_ready=result.get('production_ready'))
    packet=(LIVE/'cpu-int32-reference.packet').read_text().splitlines()
    header=packet[0].split()
    assert len(header)==7 and header[4]=='cpu-int32-reference'
    request=(LIVE/'request.txt').read_text().split()
    assert header[1:4]==request[1:4]
    summary['backends']['cpu-int32-reference']=dict(status=int(header[5]),piece_count=int(header[6]))
    (LIVE/'pc-references.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary['backends'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
