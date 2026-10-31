"""Package the frozen, board-accepted CPU80 tree; never build or program FPGA."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,sys
from zipfile import ZipFile,ZIP_DEFLATED
sys.dont_write_bytecode=True
from verify_cpu80_delivery import validate,check_zip,RUN,CPU,RTL,BIT,need,sha

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--preparation',type=Path,required=True);ap.add_argument('--soc-commit',required=True)
ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe')
ap.add_argument('--manifest-only',action='store_true');a=ap.parse_args()
root=a.root.resolve();need(not a.output.exists(),'Delivery ZIP already exists')
need(sha(Path(__file__).with_name('verify_cpu80_delivery.py'))==sha(root/'scripts/verify_cpu80_delivery.py'),'Packaged verifier differs from executed verifier')
prep=json.loads(a.preparation.read_text(encoding='utf-8'))
files={}
for q in sorted(root.rglob('*')):
    if not q.is_file():continue
    n=q.relative_to(root).as_posix()
    if n=='CPU80_DELIVERY.json' or '__pycache__' in q.parts or q.suffix in ['.pyc','.o','.vvp'] or n.startswith(('build/','.git/','review-extras/')):continue
    need(not q.is_symlink(),'Linked delivery input');files[n]=sha(q)
record=dict(schema=1,status='CPU80_BOARD_VERIFIED_DELIVERY',created_utc=datetime.now(timezone.utc).isoformat(),
    run_id=RUN,cpu_implementation_commit=CPU,soc_implementation_commit=a.soc_commit,
    cpu_rtl_sha256=RTL,bitstream_sha256=BIT,cpu_hz=80000000,sys_mac_clint_hz=49500000,
    sd_readonly_payloads=prep['sd_readonly_payloads'],files_sha256=files,
    document_visual_qa='Derived DOCX included as unrendered supporting draft; Markdown is authoritative. LibreOffice/Poppler unavailable.',
    limitations=['Existing external I/O delay coverage gaps61/128 remain.','NNUE10ms and trained YOLO full-frame30fps remain separate unaccepted targets.'],
    verification='Independent extraction, source/evidence checks and complete packaged regression must finish before remote main push.',
    delivery_scope='Exact accepted CPU80 hardware/software/runtime and paired CPU source; no Flash or SD writing.')
(root/'CPU80_DELIVERY.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
proof=validate(root,a.host_gcc)
print(json.dumps(proof),flush=True)
if a.manifest_only:sys.exit(0)
part=a.output.with_suffix(a.output.suffix+'.part');need(not part.exists(),'Existing partial archive must be preserved')
with ZipFile(part,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
    for n in files:z.write(root/n,'SOC/'+n)
    z.write(root/'CPU80_DELIVERY.json','SOC/CPU80_DELIVERY.json')
check_zip(part)
part.replace(a.output)
print(json.dumps(dict(status='CPU80_DELIVERY_ZIP_CREATED_EXTRACTION_PENDING',path=str(a.output),sha256=sha(a.output),bytes=a.output.stat().st_size)),flush=True)
