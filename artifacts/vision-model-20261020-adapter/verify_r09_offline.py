"""Source-bound Linux host, preprocessing, model-format and RV32 compile gates."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def wsl(p):
    return '/mnt/' + p.drive[0].lower() + '/' + p.as_posix()[3:]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    clone = out / 'isolation'
    def run(command, name, timeout=300, cwd=REPO):
        with (out / (name + '.log')).open('wb') as log:
            subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        print('R09_OFFLINE_GATE_PASS', name, flush=True)
    run(['git', 'clone', '--quiet', '--shared', '--no-hardlinks', '--no-checkout', str(REPO), str(clone)], 'clone')
    run(['git', '-C', str(clone), 'config', 'core.longpaths', 'true'], 'longpaths')
    run(['git', '-C', str(clone), 'checkout', '--quiet', '--detach', 'HEAD'], 'checkout')
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=REPO).decode().split('\0')
    inputs = {}
    for name in set(names) - {''}:
        if Path(name).parts[0] not in {'linux', 'sw', 'scripts'}:
            continue
        src = REPO / name
        if not src.is_file():
            continue
        inputs[name] = sha(src)
        dst = clone / name; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (out / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n', encoding='utf-8')
    run(['wsl', '-d', 'Ubuntu-22.04', '--', 'sh', wsl(clone / 'linux/vision/test_host.sh')], 'linux-host')
    assert 'PICTURE_LINUX_HOST_TEST_PASS' in (out / 'linux-host.log').read_text(encoding='utf-8')
    run(['wsl', '-d', 'Ubuntu-22.04', '--', 'sh', wsl(HERE / 'build_native.sh'), wsl(REPO),
         wsl(out / 'rv32'), wsl(REPO / 'build/picture-r09-20261021/models-r01'), 'rv32'], 'rv32')
    # Additional Linux-only gates need Torch/OpenCV and ctypes, executed by a
    # short helper below. No device transport is opened.
    helper = out / 'formats-and-pixels.py'
    helper.write_text('''import ctypes as C,json,struct,zlib,sys,subprocess,os
from pathlib import Path
repo=Path("''' + wsl(REPO) + '''")
out=Path("''' + wsl(out) + '''")
adapter=repo/'artifacts/vision-model-20261020-adapter'
sys.path.insert(0,str(adapter))
libpath=repo/'build/picture-r09-20261021/native-tests-r01/graphs.so'
lib=C.CDLL(str(libpath));lib.xqn_load.argtypes=[C.c_char_p];lib.xqn_load.restype=C.c_void_p
lib.xqn_free.argtypes=[C.c_void_p];lib.xqn_input_side.argtypes=[C.c_void_p];lib.xqn_input_side.restype=C.c_uint
checks={}
for name,root,side in [('v1_640',repo/'build/picture-p21-native/model-r02',640),('v2_416',repo/'build/picture-r09-20261021/models-r01',416)]:
 p=lib.xqn_load(str(root/'detector.xqm').encode());assert p and lib.xqn_input_side(p)==side;lib.xqn_free(p);checks[name]=True
raw=bytearray((repo/'build/picture-r09-20261021/models-r01/detector.xqm').read_bytes())
for label,shape in [('320_forbidden',(3,320,320,0)),('reserved',(3,416,416,1)),('channels',(1,416,416,0)),('rectangular',(3,416,640,0))]:
 b=bytearray(raw);struct.pack_into('<4I',b,48,*shape);struct.pack_into('<I',b,44,zlib.crc32(b[48:]));f=out/(label+'.xqm');f.write_bytes(b)
 assert not lib.xqn_load(str(f).encode()),label;f.unlink();checks[label+'_rejected']=True
from verify_r08_host import geometry_tests
checks['geometry_state_machine']=geometry_tests(repo/'build/picture-r09-20261021/native-host-r04')
(out/'formats.json').write_text(json.dumps(checks,indent=2)+'\\n')
roi=out/'roi.so'
subprocess.run(['cc','-O2','-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror','-I'+str(repo/'linux/vision'),'-I'+str(repo/'sw/xiangqi'),str(repo/'linux/vision/xq_roi.c'),str(repo/'linux/vision/xq_grid.c'),str(repo/'linux/vision/xq_vision.c'),str(repo/'sw/xiangqi/xiangqi_search.c'),str(repo/'sw/xiangqi/xiangqi_pikafish_link.c'),'-lm','-o',str(roi)],check=True,timeout=120)
subprocess.run([sys.executable,'-B',str(repo/'scripts/test_picture_roi_cv.py'),str(roi),'/home/dogandlamb/picture-p20-20261020/venv/lib/python3.10/site-packages',str(out/'pixels.json')],cwd=repo,check=True,timeout=120)
print('R09_FORMAT_GEOMETRY_PIXELS_PASS')
''', encoding='utf-8', newline='\n')
    run(['wsl', '-d', 'Ubuntu-22.04', '--', '/home/dogandlamb/picture-p20-20261020/venv/bin/python', '-B', wsl(helper)], 'formats-pixels')
    assert all(sha(REPO/k) == sha(clone/k) == v for k, v in inputs.items())
    assert (out / 'rv32/source-before.sha256').read_bytes() == (out / 'rv32/source-after.sha256').read_bytes()
    elf = (out / 'rv32/elf-inspection.txt').read_text()
    assert 'ELF32' in elf and 'RISC-V' in elf and 'rv32i' in elf
    report = dict(status='PASS', scope='Linux host tests, synthetic pixels and offline RV32 compile only',
                  hardware_used=False, deployed=False, source_stable_during_run=True, inputs=inputs,
                  linux_host_pass=True, formats=json.loads((out/'formats.json').read_text()),
                  pixels=json.loads((out/'pixels.json').read_text()),
                  rv32_binary_sha256=sha(out/'rv32/xq-native-worker'), rv32_bytes=(out/'rv32/xq-native-worker').stat().st_size,
                  transcripts={n: sha(out/(n+'.log')) for n in ('linux-host','rv32','formats-pixels')},
                  full_suite_passed=False, full_suite_blocker='Unchanged GCC16.2 --disable-lto; original LTO gate remains mandatory')
    a.receipt.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
