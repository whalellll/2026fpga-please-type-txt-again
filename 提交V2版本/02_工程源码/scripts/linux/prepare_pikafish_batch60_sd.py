"""Prepare and verify a CPU60 trial SD folder. No removable-media/device access."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, shutil, struct, subprocess, sys, zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from build_cpu80_conv_sd import cpio_entries, fdt_properties, wsl_path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p, obj): p.write_text(json.dumps(obj, indent=2)+'\n', encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--attempt', required=True)
    ap.add_argument('--base-kit', type=Path, default=Path('G:/fpga/performance_soc_pikafish_dedicated_20261024/build/dedicated-sd-04'))
    ap.add_argument('--voice', type=Path, default=Path('G:/fpga/performance_soc_voice_nnue75_20261023/build/voice-runtime-05'))
    a=ap.parse_args();assert a.attempt.isdigit()
    work=ROOT/'build'/('batch60-sd-inputs-'+a.attempt)
    out=ROOT/'build'/('batch60-sd-'+a.attempt)
    assert not work.exists() and not out.exists(), 'Preserve prior attempts; choose a new number'
    work.mkdir(parents=True);commands=[]
    def run(name, args, expected=0):
        p=subprocess.run(list(map(str,args)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
        (work/name).write_bytes(p.stdout)
        commands.append(dict(command=list(map(str,args)),exit_code=p.returncode,log=name,sha256=sha(work/name)))
        assert p.returncode==expected,(name,p.returncode,p.stdout[-2000:])
        return p.stdout
    try:
        candidate=read(ROOT/'docs/validation/pikafish-batch60-20261024/candidate-result.json')
        assert candidate['status']=='CPU60_BATCH_ROUTED_STA_VERIFIED_CANDIDATE_NOT_BOARD_OR_DELIVERY'
        native=Path(candidate['native_root']);snapshot=read(native/'pds/build_snapshot.json')
        assert candidate['cpu_hz']==60000000 and candidate['sys_hz']==49500000
        bit=ROOT/candidate['bitstream']['path'];assert sha(bit)==candidate['bitstream']['sha256']
        hardware={n:h for n,h in snapshot['inputs'].items() if n.startswith(('rtl/','ip/','config/')) or n.endswith(('.fdc','.rcf','.pcf'))}
        assert len(hardware)>50
        for n,h in hardware.items():assert sha(ROOT/n)==sha(native/n)==h,n
        engine=ROOT/'build/batch60-runtime-rv32-01';er=read(engine/'result.json')
        for n,h in er['sources_sha256'].items():assert sha(ROOT/n)==h,n
        assert er['pipeline_integration']['batch_scalar_fallback_guards']==3
        kr=ROOT/'build/batch60-kernel-01';kb=read(kr/'build.json')
        assert kb['status']=='VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD'
        for n,h in kb['inputs_sha256'].items():assert sha(Path(n))==h,n
        kernel=work/'kernel';kernel.mkdir();shutil.copy2(kr/'build.json',kernel/'build.json')
        for n,h in kb['outputs_sha256'].items():
            assert sha(kr/'outputs'/n)==h,n
            shutil.copy2(kr/'outputs'/n,kernel/n)
        check=work/'pikafish-batch-check'
        cc=['wsl.exe','-d','pikafish-verify','--','env','PATH=/opt/toolchain/bin:/usr/bin:/bin']
        run('capability-build.log',cc+['riscv32-linux-musl-gcc','-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static','-Os','-Wall','-Wextra','-Werror','-I',wsl_path(ROOT/'linux/mac_accel'),wsl_path(ROOT/'linux/mac_accel/pango_mac_batch_check.c'),'-o',wsl_path(check)])
        elf=check.read_bytes();assert elf[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<H',elf,18)[0]==243 and struct.unpack_from('<I',elf,36)[0]==0
        attrs=run('capability-elf.log',cc+['riscv32-linux-musl-readelf','-h','-A','-l',wsl_path(check)])
        assert b'INTERP' not in attrs, 'Capability guard must be static'
        missing=run('capability-no-device.log',cc+['qemu-riscv32',wsl_path(check)],expected=1)
        assert b'PIKAFISH_BATCH_CAPABILITY_FAIL open' in missing
        host=work/'capability-host-test'
        run('capability-host-build.log',cc+['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',wsl_path(ROOT/'linux/mac_accel'),wsl_path(ROOT/'sim/test_pikafish_batch_capability.c'),'-o',wsl_path(host)])
        assert b'BATCH_CAPABILITY_FAULT_CASES_PASS cases=8' in run('capability-host-test.log',cc+[wsl_path(host)])
        prepared=work/'prepared'
        run('prepare.log',[sys.executable,'-X','utf8',ROOT/'scripts/linux/prepare_voice_nnue_boot.py','--output',prepared,'--engine',engine,'--voice',a.voice,'--base-kit',a.base_kit,'--require-pipeline-hooks','--batch60','--batch-check',check])
        run('assemble.log',[sys.executable,'-X','utf8',ROOT/'scripts/linux/assemble_audio_service_sd.py','--base-kit',prepared,'--kernel',kernel,'--output',out,'--voice-nnue','--batch60','--local-oracle'])
        manifest=read(out/'manifest.json')
        assert manifest['status']=='PIKAFISH_BATCH60_RUNTIME_18_OFFLINE_TESTS_PASS_BOARD_PENDING'
        assert manifest['cpu_hz']==60000000 and manifest['batch_default'] and len(set(manifest['tests']))==18
        for n in manifest['tests']:assert b'HOST_TEST_PASS ' in (out/'evidence'/n).read_bytes()
        names={'Image','Image.mmode','fw_jump.bin','rootfs.cpio','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk'}
        assert set(manifest['sd_root_files'])==names
        assert {p.name for p in (out/'sd-root').iterdir()}==names|{'SHA256SUMS.txt'}
        for n,v in manifest['sd_root_files'].items():assert sha(out/'sd-root'/n)==v['sha256'] and (out/'sd-root'/n).stat().st_size==v['bytes']
        for v in manifest['payloads']:
            data=(out/'sd-root'/v['name']).read_bytes();assert f'{zlib.crc32(data):08x}'==v['crc32']
        rootfs=(out/'sd-root/rootfs.cpio').read_bytes();entries=cpio_entries(rootfs)
        rows={v['name'].removeprefix('./'):v for v in entries};assert len(rows)==len(entries)
        for n,h in manifest['runtime_sha256'].items():assert rows[n]['sha256']==h,n
        assert len(rootfs)<0x1000000 and sha(out/'sd-root/Image')==kb['outputs_sha256']['Image']
        blob=(out/'sd-root/soc.dtb').read_bytes();props=fdt_properties(blob)
        get=lambda n:struct.unpack_from('>I',blob,props[n][0])[0]
        assert get('/cpus/timebase-frequency')==get('/cpus/cpu@0/clock-frequency')==60000000
        assert get('/chosen/linux,initrd-start')==0x03000000 and get('/chosen/linux,initrd-end')==0x03000000+len(rootfs)
        assert blob==(out/'sd-root/mmode.dtb').read_bytes()
        def content(n):
            row=rows[n];start=row['end']-((row['bytes']+3)//4*4)
            return rootfs[start:start+row['bytes']]
        init=content('etc/init.d/S95pikafish');env=content('etc/pikafish-batch.env')
        assert b'. /etc/pikafish-batch.env' in init and init.index(b'/usr/bin/pikafish-batch-check >/dev/console')<init.index(b'XQ_GUI_INPUT=')
        assert b'PIKAFISH_NNUE_BATCH=${PIKAFISH_NNUE_BATCH:-1}' in env
        for n in ['etc/init.d/S95pikafish','etc/pikafish-batch.env','usr/bin/pikafish-batch']:
            target=work/(Path(n).name+'.sh');target.write_bytes(content(n));run(target.name+'.syntax.log',cc+['sh','-n',wsl_path(target)])
        envpath=wsl_path(work/'pikafish-batch.env.sh')
        for value in ['1','0']:
            shell=work/('check-env-'+value+'.sh')
            shell.write_text('set -eu\n'+('unset PIKAFISH_NNUE_BATCH\n' if value=='1' else 'export PIKAFISH_NNUE_BATCH=0\n')+f'. "$1"\ntest "$PIKAFISH_NNUE_BATCH" = {value}\ntest "$PIKAFISH_MAC_REQUIRE_DRIVER" = 1\n',newline='\n')
            run('batch-env-'+value+'.log',cc+['sh',wsl_path(shell),envpath])
        shutil.copy2(bit,out/'soc_top.sbit');assert sha(out/'soc_top.sbit')==candidate['bitstream']['sha256']
        binding=dict(status='PIKAFISH_BATCH60_SD_OFFLINE_READY_NOT_WRITTEN_NOT_BOARD',created_utc=datetime.now(timezone.utc).isoformat(),
            native_run_id=candidate['run_id'],implementation_commit=candidate['implementation_commit'],physical_tool_commit=candidate['physical_tool_commit'],
            native_candidate_manifest_sha256=sha(ROOT/'docs/validation/pikafish-batch60-20261024/candidate-result.json'),
            manifest_sha256=sha(out/'manifest.json'),bitstream_sha256=sha(out/'soc_top.sbit'),sd_root_files=manifest['sd_root_files'],
            rootfs_headroom_bytes=0x1000000-len(rootfs),batch_default=True,loader_prefix='PIKAFISH_BATCH60',offline_loader_tests=18,
            checked_hardware_inputs_sha256=hardware,kernel_build_receipt_sha256=sha(kr/'build.json'),runtime_receipt_sha256=sha(engine/'result.json'),
            capability_source_sha256=sha(ROOT/'linux/mac_accel/pango_mac_batch_check.c'),capability_binary_sha256=sha(check),
            sources_sha256={n:sha(ROOT/n) for n in ['scripts/linux/prepare_pikafish_batch60_sd.py','scripts/linux/prepare_voice_nnue_boot.py','scripts/linux/assemble_audio_service_sd.py','linux/mac_accel/pango_mac_uapi.h','sim/test_pikafish_batch_capability.c']},
            physical_sd_written=False,board_tested=False,flash_written=False,remote_pushed=False,formal_delivery=False)
        write(out/'trial-binding.json',binding)
        write(work/'result.json',dict(status=binding['status'],commands=commands,output=str(out),binding_sha256=sha(out/'trial-binding.json')))
        print(binding['status']);print(out/'sd-root')
    except Exception:
        write(work/'result.json',dict(status='FAILED_PRESERVED_NO_PHYSICAL_SD_WRITE',commands=commands,output=str(out)))
        raise

if __name__=='__main__':main()
