"""Create explicit serial command specs for the paired CPU60 board candidate."""
from pathlib import Path
import argparse,json
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
def save(name,commands): (o/(name+'.json')).write_text(json.dumps(commands,indent=2)+'\n')
def cmd(text,timeout=90,markers=None,allowed=None):
    d=dict(command=text,timeout=timeout)
    if markers:d['markers']=markers
    if allowed:d['allowed_exit']=allowed
    return d
save('sanity',[
    cmd('test -c /dev/pango-mac0 && test -c /dev/pango-voice0 && test -x /usr/bin/run-voice-stream-bench && echo JOINT60_DEVICES_READY; devmem 0x1fe00314; devmem 0x1fe00318; devmem 0x1fe10040',markers=['JOINT60_DEVICES_READY','0x03938700','0x02F34F60','0x56333231']),
    cmd('sha256sum /usr/bin/xqvoice-small-cnn /opt/voice2/balanced24.bin /opt/integrated60/assets/classifier.xqm /opt/integrated60/assets/board.xqm /opt/integrated60/assets/detector.xqm',markers=[
        'f76ecc1945c9bfec920c7045274a22677cc1df4b4b11fcc470b0bf5173ce1d36',
        '3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973',
        'fc03674b9f73f8c0d0fffd1cbdd10b4edebccd2056740d8aeec7e472b522697f',
        'fbd8a4e8bcd78918a44674eb69225f7d82ac4547ac24a777ea4b4b11cf495efe',
        'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d']),
    cmd('/usr/bin/xqvoice-small-cnn --selftest',markers=['PASS requant']),
    cmd('date +%s; sleep 2; date +%s',timeout=10)])
voice=[]
for ms in [500,1000,2000]:
    for repeat in range(3):
        for mode in ['wav-batch','wav-stream']:
            voice.append(cmd(f'/usr/bin/timeout 30 /usr/bin/xqvoice-small-cnn /opt/voice2/balanced24.bin /opt/integrated60/assets/voice-{ms}.wav /dev/null mac {mode}',timeout=40,
                markers=['backend=mac','VOICE_STREAM_TIMING source=wav-replay','paced=1','streamed='+str(int(mode=='wav-stream'))]))
save('voice',voice)
picture=[]
for backend in ['vision32','cpu']:
    picture.append(cmd(f'/usr/bin/timeout 300 /usr/bin/picture-new-bench classifier /opt/integrated60/assets/classifier.xqm /opt/integrated60/assets/classifier.f32 1 {backend} 3',timeout=310,
        markers=['PICTURE_TIMING model=classifier','backend='+backend,'output_crc=805678c7']))
save('classifier',picture)
save('board-image',[cmd(f'/usr/bin/timeout 600 /usr/bin/picture-new-bench board /opt/integrated60/assets/board.xqm /opt/integrated60/assets/board.f32 1 {b} 1',timeout=610,
    markers=['PICTURE_TIMING model=board','backend='+b,'output_crc=d830c1cd']) for b in ['vision32','cpu']])
save('classifier32',[cmd(f'/usr/bin/timeout 600 /usr/bin/picture-new-bench classifier /opt/integrated60/assets/classifier.xqm /opt/integrated60/assets/classifier32.f32 32 {b} 1',timeout=610,
    markers=['PICTURE_TIMING model=classifier batch=32','backend='+b,'output_crc=5c18a3d4']) for b in ['vision32','cpu']])
save('detector',[cmd('/usr/bin/timeout 900 /usr/bin/picture-new-bench detector /opt/integrated60/assets/detector.xqm /opt/integrated60/assets/detector.f32 1 vision32 1',timeout=910,
    markers=['PICTURE_TIMING model=detector','backend=vision32','output_crc=97265de4'])])
common='NNUE_VECTORS=/opt/pikafish/cpu75-nnue.vectors NNUE_SAMPLES=20 '
save('pikafish',[
    cmd(common+'PIKAFISH_STAGEA_ACCEL=0 PIKAFISH_STAGEB_ACCEL=0 PIKAFISH_NNUE_PIPELINE=0 NNUE_REQUIRE_HW=0 /usr/bin/pikafish-nnue-latency-clint',timeout=240,markers=['NNUE_LATENCY_CORRECTNESS_PASS']),
    cmd(common+'PIKAFISH_MAC_REQUIRE_DRIVER=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=1 PIKAFISH_NNUE_PIPELINE=1 NNUE_REQUIRE_HW=1 /usr/bin/pikafish-nnue-latency-clint',timeout=240,
        markers=['NNUE_LATENCY_CORRECTNESS_PASS','NNUE_DEDICATED_CACHE'],allowed=[0,2])])
print('JOINT60_BOARD_COMMAND_SPECS_READY')
