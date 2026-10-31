"""Compare all recorded fixed-input model trials against the merged CPU60 parent.

This compares end-to-end model timings, not physical camera accuracy or FPS.
CoreMark uses its separate same-round ABAB contract.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,statistics

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def need(value,message):
    if not value: raise ValueError(message)

def group(root,name):
    r=read(root/(name+'.result.json'));u=root/(name+'.uart')
    need(r['status']=='BOARD_COMMAND_SPEC_PASS' and sha(u)==r['uart_sha256'],'Failed/changed model group '+str(root/name))
    need(r['commands'] and all(x['exit'] in (0,2) for x in r['commands']),'Unexpected command failure')
    return u.read_text(errors='replace').replace('\r','')

def metrics(root):
    text=group(root,'nnue')
    need(text.count('NNUE_LATENCY_CORRECTNESS_PASS')==6 and text.count('fallbacks=0 mismatches=0')==6,'NNUE correctness/fallback evidence incomplete')
    result={}
    for phase in ('cold','warm'):
        rows=re.findall(r'NNUE_LATENCY phase='+phase+r' samples=200 mean_us=(\d+)',text)
        need(len(rows)==6,'Require all six NNUE trials per phase')
        modes=re.findall(r'NNUE_ACCUM_RESIDENT phase='+phase+r' enabled=([01]) ',text)
        need(modes==['0']*3+['1']*3,'NNUE resident modes/trials differ')
        for mode in (0,1): result[f'nnue_{phase}_resident{mode}']=[int(x) for x in rows[mode*3:mode*3+3]]
    text=group(root,'vision')
    for model,crc,count in [('classifier','27a71709',3),('board','d830c1cd',1)]:
        rows=re.findall(r'PICTURE_TIMING model='+model+r' batch=1 backend=vision32 repeat=\d+ infer_us=(\d+)[^\n]*output_crc='+crc+r' no_fallback=1',text)
        need(len(rows)==count,'Image golden/trials differ: '+model);result['image_'+model]=list(map(int,rows))
    rows=re.findall(r'INTEGER_TIMING repeat=0 graph_us=(\d+)[^\n]*output_crc=97265de4 float_ops=0 layout=HWC no_fallback=1',text)
    need(len(rows)==1 and 'e7c03029168e2ef7493733d9edd114c8326b2adec8653e374a4ea8aeec6887a9' in text,'Detector full-head golden differs')
    result['integer_detector_graph']=list(map(int,rows))
    text=group(root,'voice')
    for ms,crc in [(500,'65eda2e3'),(1000,'6611d8b0'),(2000,'b438913c')]:
        rows=re.findall(r'VOICE_STREAM_TIMING [^\n]*feature_crc='+crc+r'[^\n]*endpoint_to_result_us=(\d+)',text)
        need(len(rows)==1,'Voice feature/endpoint trial missing');result[f'voice_{ms}ms_endpoint']=list(map(int,rows))
    return result

def compare(control,candidate):
    before,after=metrics(control),metrics(candidate)
    rows={}
    for key in before:
        a,b=statistics.mean(before[key]),statistics.mean(after[key])
        need(a>0 and b>0,'Invalid latency')
        rows[key]=dict(control_samples_us=before[key],candidate_samples_us=after[key],
                       control_mean_us=a,candidate_mean_us=b,change_percent=(b/a-1)*100,nonregression=b<=a)
    need(all(x['nonregression'] for x in rows.values()),'End-to-end model latency regressed')
    return dict(status='PARENT_CPU60_TO_CPU70_ALL_RECORDED_MODEL_MEANS_NONREGRESSION_PASS',
                comparison_scope='Same fixed inputs/runtime/models; parent measured2026-10-26/27 and candidate2026-10-27. Not same-round ABAB, camera accuracy or30fps acceptance.',
                metrics=rows,nnue_10ms_goal='MISSED_RETAINED',physical_camera_acceptance=False)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--control-root',type=Path,required=True)
    ap.add_argument('--candidate-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    for role,root in [('control',a.control_root),('candidate',a.candidate_root)]:
        d=a.output/role;d.mkdir()
        for group_name in ('nnue','vision','voice','identity'):
            source=root/('board-tests-02' if group_name in ('nnue','identity') else 'board-tests-03') if role=='control' else root
            for suffix in ('.uart','.result.json'):
                shutil.copyfile(source/(group_name+suffix),d/(group_name+suffix))
        text=group(d,'identity')
        need(('0x03938700' if role=='control' else 'MAIN70_MMIO_CLOCK_PASS') in text,'Measured CPU identity missing')
    result=compare(a.output/'control',a.output/'candidate')
    result['files_sha256']={p.relative_to(a.output).as_posix():sha(p) for p in a.output.rglob('*') if p.is_file()}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
