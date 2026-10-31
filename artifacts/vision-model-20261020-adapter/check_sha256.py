import argparse,ctypes as C,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
libpath=a.out/'libsha.so';subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra','-Werror','-fPIC','-shared',str(HERE/'runtime/xq_sha256.c'),'-o',str(libpath)],check=True)
lib=C.CDLL(str(libpath.resolve()));lib.xq_sha256_hex.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p]
cases=[b'',b'abc',b'a'*1000000]+[bytes((i*37+9)%256 for i in range(n)) for n in [1,3,55,56,57,63,64,65,127,128,129,4097]]
for data in cases:
    inp=C.create_string_buffer(data);out=C.create_string_buffer(65);lib.xq_sha256_hex(inp,len(data),out)
    assert out.value.decode()==hashlib.sha256(data).hexdigest()
(a.out/'result.json').write_text(json.dumps(dict(status='PASS',cases=len(cases),scope='C SHA256 vs Python hashlib boundary/long-message checks',
    source_sha256=hashlib.sha256((HERE/'runtime/xq_sha256.c').read_bytes()).hexdigest()),indent=2)+'\n')
print('TENSOR_SHA256_TEST_PASS',len(cases))
