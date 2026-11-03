"""Build a separate e42 kernel with bounded bulk word-I/O barriers.

Copies the exact retained PN07 kernel tree. Never edits that tree, boot files,
media, FPGA state, or the selected kernel. A board comparison is still required.
"""
from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess,uuid
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--copy-proof',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    base=workspace_path(a.base);record=json.loads((base/'result.json').read_text())
    assert record['status']=='E42_PRIVATE_KERNEL_BUILD_PASS_NOT_BOARD'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(base/'Image')==record['outputs_sha256']['Image']=='63f653feae8323a1512a3f9fb38fb485c75d4b81e45c6f786675861da94618db'
    assert sha(base/'kernel.config')==record['outputs_sha256']['kernel.config']
    proof=workspace_path(a.copy_proof);tested=json.loads(proof.read_text())
    assert tested['status']=='WORD_SAFE_BULK_BOUNDARIES_HOST_RV32_SANITIZERS_NEGATIVE_CONTROLS_PASS_NOT_BOARD'
    for name,value in tested['sources_sha256'].items():assert sha(ROOT/name)==value
    for name,value in record['inputs_sha256'].items():
        p=Path(name)
        if p.name!='pango_mac_io32.h':assert sha(p)==value,'Retained kernel source changed: '+name
    inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'linux/mac_accel/kernel/pango_mac_io32.h',proof,base/'result.json',base/'Image',base/'kernel.config']}
    inputs.update({name:value for name,value in record['inputs_sha256'].items() if Path(name).name!='pango_mac_io32.h'})
    native=record['native_work']+'/source'
    assert re.fullmatch(r'/var/tmp/xinyi-kernel-[a-z0-9-]+/source',native)
    work='/var/tmp/xinyi-kernel-bulk-'+uuid.uuid4().hex;tree=work+'/source'
    commands=[]
    def run(name,args,seconds=120):
        commands.append(dict(name=name,argv=args,timeout_seconds=seconds))
        with (out/(name+'.log')).open('xb') as f:p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5',str(seconds),*args],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-3000:])
    run('verify-native-image',['sh','-c',"printf '%s  %s\\n' "+shlex.quote(record['outputs_sha256']['Image'])+' '+shlex.quote(native+'/arch/riscv/boot/Image')+' | sha256sum -c -'])
    original_files=[native+'/'+name for name in ['arch/riscv/boot/Image','.config','drivers/misc/pango_mac_io32.h','drivers/misc/Makefile']]
    run('original-before',['sha256sum',*original_files])
    run('create-work',['mkdir',work])
    run('copy-owned-tree',['cp','-a','--reflink=auto',native,tree],180)
    run('copy-header',['cp',wsl_path(ROOT/'linux/mac_accel/kernel/pango_mac_io32.h'),tree+'/drivers/misc/pango_mac_io32.h'])
    run('enable-private-object',['sh','-c',"printf '\\nCFLAGS_pango_mac.o += -DPANGO_MAC_IO32_BULK=1\\n' >> "+shlex.quote(tree+'/drivers/misc/Makefile')])
    run('kernel',['make','-s','-C',tree,'-j2','ARCH=riscv','CROSS_COMPILE=riscv64-linux-gnu-','Image'],900)
    for name,source in [('Image','arch/riscv/boot/Image'),('kernel.config','.config'),('pango_mac.o','drivers/misc/pango_mac.o')]:
        run('save-'+name,['cp',tree+'/'+source,wsl_path(out/name)])
    run('driver-disassembly',['sh','-c','riscv64-linux-gnu-objdump -dr '+shlex.quote(tree+'/drivers/misc/pango_mac.o')+' > '+shlex.quote(wsl_path(out/'driver.asm'))])
    run('original-after',['sha256sum',*original_files])
    assert (out/'original-before.log').read_bytes()==(out/'original-after.log').read_bytes()
    assert sha(out/'kernel.config')==sha(base/'kernel.config')
    assert all(sha(Path(p))==h for p,h in inputs.items())
    result=dict(status='E42_BULK_IO32_INCREMENTAL_KERNEL_BUILD_PASS_NOT_BOARD',base_kernel_sha256=sha(base/'Image'),
        source_inputs_sha256=inputs,source_stable=True,outputs_sha256={p.name:sha(p) for p in [out/'Image',out/'kernel.config',out/'pango_mac.o']},
        native_work=work,commands=commands,word_only_aperture=True,bounded_copy_barriers=True,unaligned_normal_ram_preserved=True,
        old_tree_unchanged=True,hardware_used=False,sd_written=False,production_ready=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
