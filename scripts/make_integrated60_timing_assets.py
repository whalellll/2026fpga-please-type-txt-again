"""Preserve existing real models for timing; synthetic weights only if explicit."""
from pathlib import Path
import argparse, array, gzip, hashlib, io, json, math, random, struct, sys, tarfile, wave, zlib
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cpu80_conv_sd import cpio_entries

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-rootfs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--synthetic-weights',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    source=a.source_rootfs.read_bytes();rows=cpio_entries(source)
    row=[r for r in rows if r['name'].endswith('/native-models.tar.gz')][-1]
    start=row['end']-((row['bytes']+3)&~3)
    packed=source[start:start+row['bytes']]
    archive=tarfile.open(fileobj=io.BytesIO(packed))
    original=json.loads(archive.extractfile('xq-native/native_manifest.json').read())
    files={};models={};seed=20261024
    for kind,name in enumerate(['board','detector','classifier']):
        data=bytearray(archive.extractfile('xq-native/'+name+'.xqm').read())
        assert hashlib.sha256(data).hexdigest()==original['models'][name]['sha256']
        h=struct.unpack_from('<10I',data,8);assert data[:8]==b'XQGRPH1\0' and h[0]==1 and h[1]==kind
        assert len(data)==48+h[8] and zlib.crc32(data[48:])==h[9]
        nodes=[struct.unpack_from('<32i',data,48+i*128) for i in range(h[2])]
        blob=48+h[2]*128;rng=random.Random(seed+kind);macs=weights=layers=0
        translation=bytes([254,255,1,2][i%4] for i in range(256))
        for n in nodes:
            if n[0]!=1:continue
            parent=n[5];ci=3 if parent==-1 else nodes[parent][1]
            k=ci*n[10]*n[11];count=n[1]*k;off=blob+n[20]
            assert blob<=off and off+count<=len(data)
            if a.synthetic_weights:
                data[off:off+count]=rng.randbytes(count).translate(translation)
                for co in range(n[1]):struct.pack_into('<i',data,blob+n[21]+co*4,rng.randrange(-16,17))
            weights+=count;layers+=1;macs+=n[1]*n[2]*n[3]*k
        struct.pack_into('<I',data,44,zlib.crc32(data[48:]))
        if not a.synthetic_weights:assert hashlib.sha256(data).hexdigest()==original['models'][name]['sha256']
        files[name+'.xqm']=bytes(data)
        models[name]=dict(nodes=h[2],quantized_layers=layers,weights=weights,macs_batch1=macs,
            original_sha256=original['models'][name]['sha256'],test_sha256=hashlib.sha256(data).hexdigest())
    assert sum(m['quantized_layers'] for m in models.values())==80
    for name,side,batch in [('board',192,1),('detector',640,1),('classifier',32,1),('classifier32',32,32)]:
        pattern=array.array('f',[(i*37%257)/256 for i in range(257)])
        if sys.byteorder!='little':pattern.byteswap()
        count=3*side*side*batch;raw=pattern.tobytes()
        files[name+'.f32']=(raw*((count+256)//257))[:count*4]
    for duration in [0.5,1.0,2.0]:
        samples=array.array('h',[int(6000*math.sin(2*math.pi*440*i/16000)) for i in range(int(16000*duration))])
        if sys.byteorder!='little':samples.byteswap()
        output=io.BytesIO()
        with wave.open(output,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(samples.tobytes())
        files['voice-'+str(int(duration*1000))+'.wav']=output.getvalue()
    manifest=dict(status='SYNTHETIC_VALUES_IN_REAL_PICTURE_NEW_GRAPHS_TIMING_ONLY_NOT_ACCURACY' if a.synthetic_weights else 'ORIGINAL_EXISTING_PICTURE_NEW_MODELS_TIMING_INPUTS_NOT_ACCURACY_ACCEPTANCE',synthetic_weights=a.synthetic_weights,seed=seed,
        source_rootfs_sha256=hashlib.sha256(source).hexdigest(),source_model_archive_sha256=hashlib.sha256(packed).hexdigest(),
        models=models,policy=('Explicit synthetic S8 weights and small biases; original topology retained.' if a.synthetic_weights else 'Existing board/detector/classifier XQGRPH1 files copied byte-exact, checked against embedded native manifest. All80 Conv/Linear nodes and original graph/weights/LUT/scales retained.')+' Input tensors and16kHz voice tones are synthetic timing inputs. Voice weights are genuine balanced24. This is not accuracy acceptance.',
        files={n:dict(bytes=len(d),sha256=hashlib.sha256(d).hexdigest()) for n,d in files.items()})
    files['TIMING_INPUTS_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w') as t:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0;t.addfile(info,io.BytesIO(data))
    (a.output/'timing-assets.tar.gz').write_bytes(gzip.compress(payload.getvalue(),mtime=0))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status=manifest['status'],models=models,archive_bytes=(a.output/'timing-assets.tar.gz').stat().st_size)))
if __name__=='__main__':main()
