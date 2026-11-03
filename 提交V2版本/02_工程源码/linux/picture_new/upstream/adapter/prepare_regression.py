"""Freeze the current SoC/host suite in a separate checkout, preserving old runs."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--revision',choices=('r01','r02','r03','r04','r05','r06'),default='r01');args=p.parse_args()
TARGET=Path('D:/picture-p21-regression-20261020'+('' if args.revision=='r01' else '-'+args.revision))
OUT=REPO/('build/picture-p21-native/regression-'+args.revision)
assert not TARGET.exists() and not OUT.exists()
subprocess.run(['git','clone','--quiet','--shared','--no-hardlinks','--no-checkout',str(REPO),str(TARGET)],check=True,timeout=180)
subprocess.run(['git','-C',str(TARGET),'config','core.longpaths','true'],check=True)
subprocess.run(['git','-C',str(TARGET),'checkout','--quiet','--detach','HEAD'],check=True,timeout=180)
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO,timeout=30)
names=set(filter(None,(git('diff','HEAD','--name-only','-z')+git('ls-files','--others','--exclude-standard','-z')).decode().split('\0')))
for name in names:
    if Path(name).parts[0] not in {'rtl','sw','ip','pds','scripts','sim','config','linux'}:continue
    src=REPO/name;assert src.is_file(),name
    dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
(TARGET/'build').mkdir(exist_ok=True)
shutil.copyfile(REPO/'pds/bootrom.hex',TARGET/'pds/bootrom.hex')
sys.path.insert(0,str(REPO/'scripts'))
from verify_board_release import regression_test_paths
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((REPO/'docs/validation/picture-roi-board-20261020/regression-final.json').read_text())
hardware={name:sha(REPO/name) for name in old['source_files_sha256']}
tests={name:sha(REPO/name) for name in regression_test_paths(REPO)}
linux={p.relative_to(REPO).as_posix():sha(p) for p in (REPO/'linux/vision').rglob('*') if p.is_file() and p.suffix in ('.c','.h','.inc','.sh','.txt')}
for p in ('linux/pikafish/xiangqi_pikafish_gui.c','linux/pikafish/xiangqi_fb_gui_linux.c'):linux[p]=sha(REPO/p)
if args.revision in ('r05','r06'):
    linux['linux/boot/v2_1_sd/source/loader.c']=sha(REPO/'linux/boot/v2_1_sd/source/loader.c')
assert all(sha(TARGET/name)==digest for name,digest in {**hardware,**tests,**linux}.items())
OUT.mkdir();(OUT/'inputs.json').write_text(json.dumps(dict(isolation=str(TARGET),sources=hardware,tests=tests,linux=linux),indent=2)+'\n')
print('P21_REGRESSION_FROZEN',len(hardware),len(tests),len(linux))
