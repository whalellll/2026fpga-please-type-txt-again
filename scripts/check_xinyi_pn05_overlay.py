"""Actual PN05/PN06 loader/FAT/GCC16 object tests with synthetic SD transport."""
from pathlib import Path
import argparse,hashlib,json,subprocess,struct,zipfile
from prepare_xinyi_cpu60_kit import ROOT,identity,require,cpio_read
from build_cpu80_conv_sd import make_fat32,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();c=a.candidate.resolve();out=a.output.resolve()
    from picture_workspace import workspace_path
    workspace_path(out)
    require(not out.exists(),'Fresh build/ test output required');out.mkdir(parents=True)
    m=json.loads((c/'manifest.json').read_text());support=c/'support';stage=c/'payloads';rows=[]
    prefix=m['prefix'];require(prefix in ['PN05','PN06','PN07','PN08','PN09','PN15'],'Known private overlay required')
    for name,v in m['source_inputs'].items():require(identity(Path(name).read_bytes())==v,'Source changed: '+name)
    fixture=c/'synthetic-loader-fat32.img';require(not fixture.exists(),'Preserve earlier fixture')
    locations=make_fat32(fixture,sorted(stage.iterdir()))
    def run(name,argv):
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*map(str,argv)],capture_output=True,timeout=180)
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        require(r.returncode==0,name+': '+(r.stdout+r.stderr).decode(errors='replace')[-1800:])
        return r.stdout+r.stderr
    inc=['-I',wsl_path(support/'boot'),'-I',wsl_path(support)]
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',*inc]
    common=[wsl_path(support/'host_test.c'),wsl_path(support/'boot/fat_ro.c'),wsl_path(support/'boot/crc32_fast.c'),wsl_path(support/'xq_camera.c')]
    run('host-object',['gcc',*flags,'-Dmain=xinyi_boot_main','-c',wsl_path(support/'loader.c'),'-o',wsl_path(out/'host-loader.o')])
    run('host-link',['gcc',*flags,*common,wsl_path(out/'host-loader.o'),'-Wl,--gc-sections','-o',wsl_path(out/'host-test')])
    run('rv32-same-object-link',['/opt/toolchain/bin/riscv32-linux-musl-gcc','-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static',*flags,*common,wsl_path(c/'rv32-loader-test.o'),'-Wl,--gc-sections','-o',wsl_path(out/'rv32-test')])
    def test(scenario,label=None,rv=False):
        name=('rv32-' if rv else 'host-')+(label or scenario)
        b=run(name,[*(['qemu-riscv32'] if rv else []),wsl_path(out/('rv32-test' if rv else 'host-test')),scenario,wsl_path(fixture),wsl_path(stage),wsl_path(support/'target-rom.bin')])
        require(('HOST_TEST_PASS '+scenario).encode() in b,'Missing completion')
        rows.append(dict(name=name,pass_=True,same_production_object=rv))
    for s in ['pass','clock','sys','timebase','capability','rom','init','io','abort','camera-busy','camera-stuck','rom-data']:test(s)
    for s in ['pass','clock','rom','camera-busy','camera-stuck']:test(s,rv=True)
    if prefix in ['PN06','PN07','PN08','PN09','PN15']:
        for rv in [False,True]:
            for s in ['old-exact','wrong-exact',*[f'engine-busy-{i}' for i in range(5)]]:test(s,rv=rv)
    def mutation(offset,data,name,scenario='reject'):
        with fixture.open('r+b') as f:f.seek(offset);old=f.read(len(data));f.seek(offset);f.write(data)
        try:test(scenario,name)
        finally:
            with fixture.open('r+b') as f:f.seek(offset);f.write(old)
    for name in [prefix+'UPD.GZ','PN04FS.BIN']+([m.get('kernel_filename',prefix+'K.BIN')] if prefix in ['PN06','PN07','PN08','PN09','PN15'] else []):
        pos=locations[name]['data']+100
        with fixture.open('rb') as f:f.seek(pos);old=f.read(1)
        mutation(pos,bytes([old[0]^1]),'corrupt-'+name)
    mutation(locations['PN04NN.PFF']['directory'],b'\xe5','missing-model','metadata')
    mutation(locations[prefix+'.DTB']['directory']+28,struct.pack('<I',1),'wrong-dtb-size','metadata')
    mutation(510,b'\0\0','bad-fat-signature')
    # Negative control: omitting explicit gap initialization must fail at jump.
    original=(support/'loader.c').read_text();needle='REG32(0x03000000u+i)=0;REG32(0x83000000u+i)=0;'
    require(original.count(needle)==1,'Unknown padding implementation')
    negative=out/'negative-loader.c';negative.write_text(original.replace(needle,'(void)i;'),newline='\n')
    run('negative-object',['gcc',*flags,'-Dmain=xinyi_boot_main','-c',wsl_path(negative),'-o',wsl_path(out/'negative.o')])
    run('negative-link',['gcc',*flags,*common,wsl_path(out/'negative.o'),'-Wl,--gc-sections','-o',wsl_path(out/'negative-test')])
    r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',wsl_path(out/'negative-test'),'pass',wsl_path(fixture),wsl_path(stage),wsl_path(support/'target-rom.bin')],capture_output=True,timeout=180)
    (out/'negative-padding.log').write_bytes(r.stdout+r.stderr)
    require(r.returncode!=0 and b'overlay alignment zeros published' in r.stderr,'Padding negative control failed')
    archive=c/(prefix.lower()+'-update.zip');require(not archive.exists(),'Preserve prior ZIP')
    names=[prefix+'BOOT.BIN',prefix+'.DTB',prefix+'UPD.GZ',prefix+'.JSN']+([prefix+'K.BIN',prefix+'.SHA'] if prefix in ['PN06','PN07','PN08','PN09','PN15'] else [])
    if prefix=='PN15':names=sorted(f.name for f in (c/'sd-update').iterdir())
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in names:z.write(c/'sd-update'/name,'sd-update/'+name)
        z.write(c/'README.txt','README.txt')
    with zipfile.ZipFile(archive) as z:
        for name in names:require(z.read('sd-update/'+name)==(c/'sd-update'/name).read_bytes(),'ZIP readback mismatch')
    require(all(identity(Path(n).read_bytes())==v for n,v in m['source_inputs'].items()),'Source changed during tests')
    result=dict(status=prefix+'_SEVEN_PAYLOAD_LOADER_HOST_SAME_GCC16_RV32_PASS_NOT_BOARD',hardware_used=False,
        sd_written=False,flash_written=False,selector_modified=False,tests=rows,padding_negative_control=True,
        package=identity(archive.read_bytes()),package_path=str(archive),
        limitations=['Synthetic FAT/UART/MMIO only. Linux overlay unpack and product startup require real board validation.'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],len(rows))

if __name__=='__main__':main()
