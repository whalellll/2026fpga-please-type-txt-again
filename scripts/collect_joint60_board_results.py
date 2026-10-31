"""Summarize actual UART measurements; missing/failed stages stay explicit."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,statistics
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def rows(text,prefix):
    return [dict(re.findall(r'(\w+)=([^\s]+)',line)) for line in text.splitlines() if line.startswith(prefix)]
def mean(items,key):return statistics.mean(int(x[key]) for x in items)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--board-root',type=Path,default=R/'build/integrated-board-program-03');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    b=a.board_root;e=a.output;assert not e.exists();e.mkdir(parents=True)
    stages={};issues=[]
    for name in ['sanity','voice','classifier','board-image','classifier32','detector','pikafish']:
        path=b/(name+'.result.json')
        stages[name]=read(path)['status'] if path.exists() else 'NOT_RUN'
        if stages[name]!='BOARD_COMMAND_SPEC_PASS':issues.append(name+':'+stages[name])
    voice=[];p=b/'voice.uart'
    if p.exists():
        text=p.read_text(errors='replace');timing=rows(text,'VOICE_STREAM_TIMING ');cnn=rows(text,'backend=')
        if len(timing)==len(cnn)==18:
            for i,(t,c) in enumerate(zip(timing,cnn)):
                assert t['source']=='wav-replay' and t['paced']=='1' and c['backend']=='mac' and int(c['mac_jobs'])>0
                assert int(t['streamed'])==i%2
            for index,ms in enumerate([500,1000,2000]):
                ts=timing[index*6:index*6+6];cs=cnn[index*6:index*6+6]
                parity=len({(t['feature_crc'],t['feature_frames'],c['text'],c['mac_jobs'],c['mac_cycles']) for t,c in zip(ts,cs)})==1
                if not parity:issues.append('voice parity '+str(ms))
                batch=ts[::2];stream=ts[1::2]
                voice.append(dict(clip_ms=ms,repeats_per_mode=3,exact_feature_crc_text_jobs_cycles_parity=parity,
                    batch_endpoint_mean_us=mean(batch,'endpoint_to_result_us'),stream_endpoint_mean_us=mean(stream,'endpoint_to_result_us'),
                    endpoint_speedup=mean(batch,'endpoint_to_result_us')/mean(stream,'endpoint_to_result_us'),
                    batch_feature_tail_mean_us=mean(batch,'feature_tail_us'),stream_feature_tail_mean_us=mean(stream,'feature_tail_us'),
                    stream_max_backlog_frames=max(int(t['max_backlog_frames']) for t in stream),feature_crc=ts[0]['feature_crc'],
                    batch_total_mean_us=mean(cs[::2],'total_us'),stream_total_mean_us=mean(cs[1::2],'total_us'),
                    stream_CNN_mean_us=mean(cs[1::2],'cnn_us'),stream_decode_mean_us=mean(cs[1::2],'decode_us'),
                    hardware_mac_cycles=int(cs[0]['mac_cycles'])))
        else:issues.append('incomplete_voice_samples:'+str((len(timing),len(cnn))))
    pictures=[]
    for name in ['classifier','board-image','classifier32','detector']:
        p=b/(name+'.uart')
        if not p.exists():continue
        rs=rows(p.read_text(errors='replace'),'PICTURE_TIMING ')
        hw=[r for r in rs if r['backend']=='vision32'];cpu=[r for r in rs if r['backend']=='cpu']
        if not hw:continue
        crc={r['output_crc'] for r in rs};okay=len(crc)==1 and all(int(r['jobs'])>0 and int(r['cycles'])>0 for r in hw)
        if not okay:issues.append('image hardware/CRC failure '+name)
        row=dict(test=name,hardware_repeats=len(hw),cpu_repeats=len(cpu),hardware_infer_mean_us=mean(hw,'infer_us'),
            hardware_counter_mean_us=mean(hw,'hardware_us'),output_crc=sorted(crc),hardware_jobs=[int(r['jobs']) for r in hw],hardware_cycles=[int(r['cycles']) for r in hw],exact_output_parity=okay)
        if cpu:row.update(cpu_infer_mean_us=mean(cpu,'infer_us'),speedup=mean(cpu,'infer_us')/mean(hw,'infer_us'))
        pictures.append(row)
    pika={};p=b/'pikafish.uart'
    if p.exists():
        rs=rows(p.read_text(errors='replace'),'NNUE_LATENCY phase=')
        if len(rs)==4:
            for i,phase in enumerate(['cold','warm']):
                assert rs[i]['phase']==rs[i+2]['phase']==phase
                pika[phase]=dict(cpu_mean_us=int(rs[i]['mean_us']),hardware_mean_us=int(rs[i+2]['mean_us']),speedup=int(rs[i]['mean_us'])/int(rs[i+2]['mean_us']),hardware_p95_us=int(rs[i+2]['p95_us']))
    files={}
    for p in b.iterdir():
        if p.is_file() and (p.suffix=='.uart' or p.name.endswith('.result.json') or p.name in ['result.json','program.json']):
            shutil.copyfile(p,e/p.name);assert sha(p)==sha(e/p.name);files[p.name]=sha(p)
    result=dict(status='JOINT60_BOARD_FUNCTIONAL_PASS_PERFORMANCE_MEASURED_STA_FAILED_NOT_RELEASE' if not issues else 'JOINT60_BOARD_MEASUREMENTS_PARTIAL_OR_FAILED_PRESERVED',
        created_utc=datetime.now(timezone.utc).isoformat(),stages=stages,issues=issues,voice=voice,picture=pictures,pikafish=pika,
        bitstream_sha256=read(b/'result.json')['bitstream_sha256'],sd_manifest_sha256=read(b/'result.json')['sd_manifest_sha256'],
        evidence_sha256=files,scope='Real CPU60 board, genuine model weights, deterministic RGB and synthetic-tone WAV inputs. Voice latency is paced WAV last sample to pre-print result; actual microphone/VAD latency and recognition accuracy are not established. Images include CPU graph operators, inference excludes file loading/camera/display. Pikafish is exact NNUE eval, not search.',
        performance_targets=dict(voice_paced_WAV_endpoint_10ms_pass=False,live_speech_end_latency='NOT_MEASURED',vision30fps_pass=False,pikafish_NNUE_10ms_pass=False),
        collector_sha256=sha(Path(__file__)),native_sta_pass=False,formal_delivery=False,flash_written=False)
    (e/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],voice=voice,picture=pictures,pikafish=pika,issues=issues),ensure_ascii=False))
if __name__=='__main__':main()
