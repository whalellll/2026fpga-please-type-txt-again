"""Execute the actual new kernel ioctl path with MMIO/time/copy stubs."""
from pathlib import Path
import argparse, hashlib, json, subprocess
ROOT=Path(__file__).resolve().parents[1]
def lin(p):
    s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    driver=ROOT/'linux/audio/kernel/pango_voice.c';header=ROOT/'linux/audio/pango_voice_uapi.h';harness=ROOT/'sim/voice_quant_driver_harness.c'
    text=driver.read_text();first=text.index('static long voice_ioctl_locked(');last=text.index('    if(v->cnn_supported)return -EOPNOTSUPP;',first)
    actual=text[first:last]+'    return -ENOTTY;\n}\n'
    (o/'test.c').write_text(harness.read_text().replace('/* ACTUAL_VOICE_CNN_IOCTL */',actual))
    cmd=f"set -eu; gcc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-variable -I'{lin(header.parent)}' '{lin(o/'test.c')}' -o '{lin(o/'test')}'; '{lin(o/'test')}'"
    r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=90)
    (o/'test.log').write_bytes(r.stdout+r.stderr)
    assert r.returncode==0 and b'ACTUAL_VOICE_QUANT_DRIVER_' in r.stdout,(r.stdout+r.stderr).decode(errors='replace')[-2500:]
    record=dict(status='ACTUAL_VOICE_QUANT_DRIVER_TRANSACTION_STUB_PASS_NOT_KERNEL_OR_BOARD',
                inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [driver,header,harness]},
                scope='Actual ioctl code, mocked registers/time/copies; scheduler and physical board are separate gates.')
    (o/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
