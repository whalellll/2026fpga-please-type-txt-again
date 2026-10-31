"""Preserve actual UART timings with their SD, CRAM and model identities."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def rows(path,prefix):
    return [dict(re.findall(r'(\w+)=([^\s]+)',s)) for s in path.read_text(encoding='utf-8').replace('\r','').splitlines() if s.startswith(prefix)]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,default=R/'build/integrated-board-program-02')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();t=a.trial.resolve();out=a.output.resolve()
    assert not out.exists()
    for n in ['sanity','voice-timing','pikafish-timing','picture-cpu']:
        assert read(t/(n+'.result.json'))['status']=='BOARD_COMMAND_SPEC_PASS',n
    boot=read(t/'sdboot.result.json');assert boot['status']=='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING'
    trial=read(t/'result.json');assert trial['bitstream_sha256']=='6c0b016b43bcae481d1187594a0546f3f7a21c4d848b6313d5c2851088b0796b'
    v=rows(t/'voice-timing.uart','backend=');assert len(v)==6
    voice=[]
    for i,ms in enumerate([500,1000,2000]):
        hw,cpu=v[2*i:2*i+2]
        assert hw['backend']=='mac' and cpu['backend']=='cpu' and hw['frames']==cpu['frames'] and hw['text']==cpu['text']
        assert int(hw['mac_jobs'])>0 and int(hw['resident_jobs'])==int(hw['mac_jobs']) and int(cpu['mac_jobs'])==0
        voice.append(dict(audio_ms=ms,cpu=cpu,hardware=hw,speedup=float(cpu['total_us'])/float(hw['total_us'])))
    p=rows(t/'pikafish-timing.uart','NNUE_LATENCY phase=');assert len(p)==4
    pikafish=[]
    for i,phase in enumerate(['cold','warm']):
        cpu,hw=p[i],p[i+2];assert cpu['phase']==hw['phase']==phase and cpu['samples']==hw['samples']=='20'
        pikafish.append(dict(phase=phase,cpu=cpu,hardware=hw,speedup=float(cpu['mean_us'])/float(hw['mean_us'])))
    body=(t/'pikafish-timing.uart').read_text(encoding='utf-8')
    assert body.count('NNUE_LATENCY_CORRECTNESS_PASS')==2 and 'NNUE_10MS_TARGET_MISS' in body
    image=rows(t/'picture-cpu.uart','PICTURE_TIMING ');assert len(image)==5
    for d in image:
        assert d['backend']=='cpu' and d['no_fallback']=='1' and d['jobs']=='0'
        expected={('classifier','1'):'805678c7',('classifier','32'):'5c18a3d4',('board','1'):'d830c1cd'}
        assert d['output_crc']==expected[d['model'],d['batch']]
    out.mkdir(parents=True)
    files={}
    paths=[t/n for n in ['result.json','program.json','sdboot.result.json','sdboot.uart','sanity.result.json','sanity.uart','voice-timing.result.json','voice-timing.uart','pikafish-timing.result.json','pikafish-timing.uart','picture-cpu.result.json','picture-cpu.uart','small-timing.result.json','small-timing.uart','diag.result.json','diag.uart']]
    paths += [R/'build/integrated-sd-kit-04/manifest.json',R/'build/integrated-real-timing-assets-02/manifest.json']
    for i,p in enumerate(paths):
        name=f'{i:02d}-'+p.name;shutil.copyfile(p,out/name);assert sha(out/name)==sha(p)
        files[name]=dict(source=str(p),sha256=sha(p),bytes=p.stat().st_size)
    result=dict(status='BOARD_VOICE_PIKAFISH_CPU_IMAGE_TIMINGS_PASS_IMAGE_HARDWARE_FAILED_NOT_ACCEPTED',
        created_utc=datetime.now(timezone.utc).isoformat(),cpu_hz=60000000,sys_hz=49500000,
        bitstream_sha256=trial['bitstream_sha256'],sd_manifest_sha256=trial['sd_manifest_sha256'],
        genuine_weights=True,synthetic_inputs=True,voice=voice,pikafish=pikafish,picture_cpu=image,
        image_hardware_status='First node failed DDR response: status0x16 error3 read32B mac_cycles0; no timing or speedup',
        flash_written=False,formal_delivery=False,files=files,
        scope='WAV processing includes model/input reads and device open, excludes live capture/endpoint. CPU voice reference also verifies packed dots; not an optimized CPU-only baseline. NNUE evaluation excludes registration/model load and is not full search. Image forward excludes camera, calibration, NMS/FEN; no30fps claim. Original bit remains functionally failed for V321; corrected RTL is a separate candidate.')
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'])

if __name__=='__main__':main()
