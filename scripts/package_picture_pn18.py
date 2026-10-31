"""Close PN18 SD members and independently exported software sources.

No hardware or physical media operations. All output stays in a new E-backed
build directory; copying a verified final ZIP to Desktop is a separate step.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import shlex
import shutil
import struct
import subprocess
import tarfile
import time
import zipfile
import zlib

from picture_workspace import ROOT, workspace_path
from prepare_xinyi_cpu60_kit import require, cpio_read, identity
from prepare_picture_pn18 import file_identity, BANK_BASE, BANK_NODE
from prepare_picture_candidate import tokens
from build_cpu80_conv_sd import wsl_path

FINAL_NAME = 'xinyi-pn18-r18-full-sd-20261029-r01.zip'
WORKER = 'efa12b64e4350373dac3620eb071cb6ed528a821772cb406ea690159d6ffb821'
ROOTFS_PATHS = dict(gui='usr/bin/xinyi-one', speech='usr/bin/xinyi-speech-worker',
                   asr='usr/bin/xqvoice-small-cnn', engine='usr/bin/xinyi-engine')


def safe_name(name):
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and ':' not in name and '\\' not in name,
            'Unsafe archive name: '+name)
    return p


def regular(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'Regular input file required: '+str(p))
    return p


def wsl_input(name):
    require(name.startswith('/mnt/') and len(name) > 7 and name[6] == '/', 'Bound WSL source expected')
    return Path(name[5].upper()+':'+name[6:])


def parse_sources(data):
    rows = []
    for line in data.decode().splitlines():
        digest, name = line.split(maxsplit=1)
        require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Invalid source digest')
        rows.append((digest, wsl_input(name)))
    return rows


class Package:
    def __init__(self, out):
        self.out, self.delivery, self.work = out, out/'DELIVERY', out/'WORK'
        self.delivery.mkdir(); self.work.mkdir()
        self.commands, self.inputs, self.objects = [], {}, {}

    def record(self, path, data):
        path = Path(path); require(not path.exists(), 'Preserve earlier output: '+str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def bind(self, path):
        path = regular(path).resolve(); info = file_identity(path)
        require(str(path) not in self.inputs or self.inputs[str(path)] == info, 'Input changed: '+str(path))
        self.inputs[str(path)] = info
        return info

    def copy(self, source, target):
        info = self.bind(source); target = Path(target)
        require(not target.exists(), 'Preserve output: '+str(target)); target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target); require(file_identity(target) == info, 'Copy mismatch')
        return info

    def run(self, name, argv, seconds=240):
        log = self.work/(name+'.log'); require(not log.exists(), 'Unique command label required')
        start = time.monotonic()
        command = ['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                   'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(list(map(str,argv)))]
        with log.open('xb') as stream:
            proc = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=seconds+20)
        self.commands.append(dict(name=name,seconds=round(time.monotonic()-start,3),exit=proc.returncode,
                                  log=file_identity(log)))
        require(proc.returncode == 0, name+': '+log.read_text(errors='replace')[-2000:])
        return log

    def source_bytes(self, path, digest):
        """Recover old tracked bytes read-only; never modify the active workspace."""
        path = Path(path)
        if path.is_file() and file_identity(path)['sha256'] == digest:
            self.bind(path); return path.read_bytes(), dict(kind='existing_exact_file',path=str(path))
        try: relative = path.relative_to(ROOT).as_posix()
        except ValueError: raise ValueError('Missing immutable source: '+str(path))
        proc = subprocess.run(['git','show','HEAD:'+relative],cwd=ROOT,capture_output=True,timeout=30)
        require(proc.returncode == 0 and hashlib.sha256(proc.stdout).hexdigest() == digest,
                'No matching existing/Git HEAD source: '+relative)
        commit = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,check=True,timeout=30).stdout.decode().strip()
        return proc.stdout, dict(kind='read_only_git_blob',commit=commit,path=relative)

    def object(self, data, digest):
        require(hashlib.sha256(data).hexdigest() == digest, 'Source object digest')
        name = 'SOURCE/objects/'+digest
        if digest not in self.objects:
            path = self.delivery/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            self.objects[digest] = name
        return name

    def archive_sources(self, label, before, after, supplemental=()):
        before_data = regular(before).read_bytes(); self.bind(before)
        require(before_data == regular(after).read_bytes(), label+' before/after mismatch'); self.bind(after)
        sources, origins = {}, {}
        for digest, path in parse_sources(before_data):
            relative = path.relative_to(ROOT).as_posix(); safe_name(relative)
            data, origin = self.source_bytes(path,digest)
            require(relative not in sources or sources[relative] == data,'Conflicting source row')
            sources[relative], origins[relative] = data, origin
        for relative in supplemental:
            path = ROOT/relative
            if path.is_file():
                self.bind(path); sources.setdefault(relative,path.read_bytes())
        folder = self.delivery/'SOURCE'/label; folder.mkdir(parents=True)
        self.copy(before,folder/'source-before.sha256'); self.copy(after,folder/'source-after.sha256')
        archive = folder/'source.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,data in sorted(sources.items()): z.writestr('source/'+name,data)
            z.writestr('manifest.json',json.dumps({n:identity(b) for n,b in sorted(sources.items())},indent=2)+'\n')
        # Re-open exact source ZIP, validate CRC/digest, extract only safe files.
        extracted = self.work/label/'source'
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None and len(z.namelist()) == len(set(z.namelist())), 'Source archive CRC/duplicates')
            for name,data in sources.items():
                blob = z.read('source/'+name); require(blob == data, 'Source ZIP readback')
                target = extracted/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(blob)
        self.record(folder/'source-manifest.json',dict(source_files={n:identity(b) for n,b in sorted(sources.items())},
                                                     bound_source_origins=origins, archive=file_identity(archive)))
        return extracted, folder, sources

    def frozen_sources(self, label, snapshot, build):
        """Rebuild archived old bytes even after a later active-source candidate."""
        old = Path(snapshot['folder']); folder = self.delivery/'SOURCE'/label
        require(self.bind(old/'source.zip') == snapshot['archive'], 'Frozen source archive identity changed')
        before = (old/'source-before.sha256').read_bytes()
        require(before == (old/'source-after.sha256').read_bytes() == (build/'source-before.sha256').read_bytes() ==
                (build/'source-after.sha256').read_bytes(), 'Frozen build source inventory mismatch')
        require(self.bind(old/'source-before.sha256') == snapshot['source_before'] and
                self.bind(old/'source-after.sha256') == snapshot['source_after'], 'Frozen inventory digest changed')
        for name in ['source.zip','source-before.sha256','source-after.sha256','source-manifest.json']:
            self.copy(old/name,folder/name)
        source = self.work/label/'source'
        with zipfile.ZipFile(folder/'source.zip') as z:
            manifest = json.loads(z.read('manifest.json'))
            require(len(z.namelist()) == len(set(z.namelist())) and z.testzip() is None and
                    set(z.namelist()) == {'source/'+n for n in manifest}|{'manifest.json'}, 'Frozen source ZIP closure')
            for digest,path in parse_sources(before):
                relative=path.relative_to(ROOT).as_posix()
                require(manifest[relative]['sha256'] == digest, 'Frozen source not equal to original compiler input')
            for name,row in manifest.items():
                safe_name(name); data=z.read('source/'+name)
                require(identity(data) == row, 'Frozen source member changed')
                target=source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return source,folder

    def software_build(self, label, build, expected, frozen=None):
        build = Path(build).resolve(); speech = label == 'speech'
        selected = ['speech-worker.elf','speech-worker','xinyi-speech-worker'] if speech else ['gui','gui.elf','xinyi-one.elf','xinyi-one']
        rawname = 'xinyi-speech-worker' if speech else 'xinyi-one'
        selected_file = next((build/n for n in selected if (build/n).is_file() and file_identity(build/n)['sha256'] == expected),None)
        if selected_file is None:
            selected_file = self.work/(label+'-original-stripped.elf')
            self.bind(build/rawname)
            self.run(label+'-strip-original',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',
                     wsl_path(selected_file),wsl_path(build/rawname)],30)
        require(file_identity(selected_file)['sha256'] == expected, label+' selected ELF does not match final rootfs')
        config_name = 'speech-config.txt' if speech else 'gui-config.txt'
        self.bind(build/config_name)
        options = dict(line.split('=',1) for line in (build/config_name).read_text().splitlines())
        require(options.get('battle_r17') == '1' and options.get('coach_move_audio') == '1', label+' requires r17 bank contract')
        if not speech:
            require((build/'cpu-hz.txt').read_text().strip() == '60000000' and options.get('asr_voice4') == '0' and
                    options.get('ui_nav_diag') == '0', 'Default balanced24 CPU60 production GUI required')
            self.bind(build/'cpu-hz.txt')
        extras = () if speech else ('linux/xinyi/gen_font.py','linux/xinyi/gen_home_art.py',
            'linux/xinyi/gen_home_background.py','linux/xinyi/gen_battle_font.py',
            'linux/xinyi/fonts/glyphs.json','linux/xinyi/fonts/source.json',
            'linux/xinyi/game_template_export_r21.c','scripts/prepare_xinyi_game_templates_r21.py',
            'scripts/prepare_xinyi_game_commands_r21.py','scripts/prepare_xinyi_game_palette_r21.py')
        if frozen: source,folder=self.frozen_sources(label,frozen,build)
        else: source, folder, _ = self.archive_sources(label,build/'source-before.sha256',build/'source-after.sha256',extras)
        self.copy(build/config_name,folder/config_name)
        if not speech: self.copy(build/'cpu-hz.txt',folder/'cpu-hz.txt')
        env = ['XINYI_'+key.upper()+'='+value for key,value in options.items()]
        if not speech: env.append('XINYI_CPU_HZ=60000000')
        target = source/'build/reproduce'; script = 'build_speech.sh' if speech else 'build.sh'
        log = self.run(label+'-export-source-build',['env',*env,'sh',wsl_path(source/'linux/xinyi_board'/script),wsl_path(target)])
        produced = self.work/(label+'-reproduced.elf')
        if file_identity(target/rawname)['sha256'] == expected:
            shutil.copyfile(target/rawname,produced); elf_form = 'build_output_exact'
        else:
            self.run(label+'-strip-reproduced',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all',
                     '-o',wsl_path(produced),wsl_path(target/rawname)],30); elf_form = 'strip_all_exact'
        require(produced.read_bytes() == selected_file.read_bytes(), label+' independently exported rebuild differs')
        # Production input proof and independent proof remain separate identities.
        proof = dict(status=label.upper()+'_SOURCE_ZIP_INDEPENDENT_REBUILD_BYTE_EXACT_PASS_NOT_BOARD',
                     selected_sha256=expected,options=options,source_zip=file_identity(folder/'source.zip'),
                     rebuilt=file_identity(produced),elf_form=elf_form,hardware_used=False)
        self.copy(log,folder/'independent-build.log'); self.record(folder/'rebuild-proof.json',proof)
        self.copy(selected_file,self.delivery/'SOFTWARE'/label/'program.rv32.elf')
        return proof

    def asr_kit(self, kit, expected):
        result_path = Path(kit) if Path(kit).is_file() else Path(kit)/'result.json'
        self.bind(result_path); result = json.loads(result_path.read_text())
        require(result['both_zip_source_rebuilds_exact'] and result['old_pn15_exact'] and not result['model_changed'],
                'ASR complete source ZIP proof required')
        require(result['programs']['flag1']['sha256'] == expected, 'ASR final timing variant mismatch')
        archive = Path(result['archive']['path']); require(self.bind(archive)['sha256'] == result['archive']['sha256'], 'ASR archive drift')
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None and len(z.namelist()) == len(set(z.namelist())), 'ASR ZIP integrity')
            m = json.loads(z.read('manifest.json')); require(set(z.namelist()) == set(m['members'])|{'manifest.json'}, 'ASR member closure')
            for name,row in m['members'].items():
                safe_name(name); data=z.read(name); require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'],'ASR member drift')
            data = z.read('software/asr-balanced24-flag1.rv32.elf')
            require(hashlib.sha256(data).hexdigest() == expected,'ASR ELF mismatch')
            software = self.delivery/'SOFTWARE/asr/program.rv32.elf'; software.parent.mkdir(parents=True); software.write_bytes(data)
            require(z.read('evidence/flag1-source.sha256'), 'ASR source evidence missing')
        self.copy(archive,self.delivery/'SOURCE/asr'/archive.name)
        self.copy(result_path,self.delivery/'SOURCE/asr/rebuild-proof.json')
        return dict(status=result['status'],selected_sha256=expected,archive=file_identity(archive),independent_rebuild_preexisting=True)

    def engine_kit(self, kit, expected):
        # A completed independent engine proof is supplied by the full-source builder.
        kit = Path(kit)
        result_path = kit if kit.is_file() else kit/'result.json'
        if not result_path.is_file() and kit.is_dir(): result_path=kit/'full-build-r01/result.json'
        self.bind(result_path); result = json.loads(result_path.read_text())
        require(result['v2']['sha256'] == expected and result['original_core_exact'] and not result['old_objects_reused'], 'Engine identity/source closure mismatch')
        proof_rows = list(result_path.parent.glob('*rebuild*json')) + list(result_path.parent.glob('*source*proof*json'))
        if result.get('independent_source_rebuild_proof'): proof_rows.insert(0,Path(result['independent_source_rebuild_proof']))
        proof_path = next((p for p in proof_rows if p.is_file() and p.resolve() != result_path.resolve()),None)
        require(proof_path is not None, 'Engine source archive independent proof required')
        proof_info = self.bind(proof_path); proof = json.loads(proof_path.read_text())
        if result.get('independent_source_rebuild_proof_sha256'):
            require(proof_info['sha256'] == result['independent_source_rebuild_proof_sha256'], 'Engine independent proof drift')
        require(proof.get('byte_exact') is True or proof.get('byte_equal') is True or
                proof.get('v2_byte_equal') is True or proof.get('full_byte_equal') is True or
                proof.get('independent_rebuild_byte_exact') is True,
                'Engine independent source rebuild did not prove byte equality')
        require(expected in json.dumps(proof), 'Engine independent proof must bind selected V2 SHA')
        source_row = result.get('final_source_archive', result['source_archive'])
        source = Path(source_row['path'])
        require(self.bind(source)['sha256'] == source_row['sha256'], 'Engine source archive drift')
        require(source_row['sha256'] in json.dumps(proof), 'Engine proof must bind this source archive SHA')
        if proof.get('elf_path'):
            require(self.bind(Path(proof['elf_path']))['sha256'] == expected, 'Engine independent rebuilt ELF drift')
        with tarfile.open(source,'r:gz') as archive:
            members = archive.getmembers(); require(len(members) == len({f.name for f in members}), 'Engine tar duplicates')
            for entry in members: safe_name(entry.name); require(entry.isfile(), 'Engine source tar contains non-regular entry')
            sums = dict((name,digest) for digest,name in (line.split('  ',1) for line in archive.extractfile('SOURCE_SHA256SUMS.txt').read().decode().splitlines()))
            require({f.name for f in members} == set(sums)|{'SOURCE_SHA256SUMS.txt'}, 'Engine source tar member closure')
            for name,digest in sums.items():
                require(hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, 'Engine tar member digest')
        binary = result_path.parent/'xinyi-engine-v2'
        require(self.bind(binary)['sha256'] == expected,'Engine final binary mismatch')
        self.copy(binary,self.delivery/'SOFTWARE/engine/program.rv32.elf')
        self.copy(source,self.delivery/'SOURCE/engine'/source.name)
        self.copy(result_path,self.delivery/'SOURCE/engine/build-proof.json')
        self.copy(proof_path,self.delivery/'SOURCE/engine/independent-rebuild-proof.json')
        return dict(status=result['status'],selected_sha256=expected,independent_rebuild_proof=file_identity(proof_path))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['pn18','gui-build','speech-build','engine-kit','asr-kit','source-bindings','output']:
        ap.add_argument('--'+name,type=Path,required=name in ['pn18','output'])
    ap.add_argument('--worker-directory',type=Path)
    ap.add_argument('--archive-name',default=FINAL_NAME,help='New immutable delivery name; prior packages remain untouched')
    ap.add_argument('--sd-only-self-test',action='store_true',help='Unselected plumbing ZIP only; never a final release')
    a = ap.parse_args(); out = workspace_path(a.output)
    require(re.fullmatch(r'xinyi-pn18-[A-Za-z0-9-]+\.zip',a.archive_name) is not None,
            'Simple unique PN18 ZIP name required')
    require(out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()) and not out.exists(),'Fresh E build output required')
    out.mkdir(parents=True); p = Package(out)
    result = dict(status='PN18_PACKAGE_FAILED_PRESERVED',hardware_used=False,sd_written=False,flash_written=False)
    try:
        pn18 = workspace_path(a.pn18); p.bind(pn18/'manifest.json'); m = json.loads((pn18/'manifest.json').read_text())
        require(m['prefix'] == 'PN18' and m['payload_count'] == 8 and len(m['full_sd_files']) == 21,'Complete PN18 required')
        require(a.sd_only_self_test or m['status'] == 'PN18_OFFLINE_FULL_SD_PREPARED_NOT_INSTALLED', 'Plumbing is not a final SD release')
        for name, expected in m['source_inputs'].items():
            require(p.bind(Path(name)) == expected,'PN18 prepared source drift: '+name)
        sd = pn18/'sd-full'; require(set(f.name for f in sd.iterdir()) == set(m['full_sd_files']),'Exact SD file list required')
        for name,row in m['full_sd_files'].items():
            safe_name(name); require(p.copy(sd/name,p.delivery/'SD_ROOT'/name) == row,'SD member identity mismatch: '+name)
        require((sd/'xiangqi.bin').read_bytes() == (sd/'PN18BOOT.BIN').read_bytes(),'ROM xqboot entry must select PN18 loader')
        binary = (sd/'xiangqi.bin').read_bytes()
        for row in m['payloads']:
            descriptor = struct.pack('<III',row['address'],row['bytes'],int(row['crc32'],16))
            require(binary.count(descriptor) == 1,'PN18 descriptor exactness')
            at=binary.index(descriptor); pointer=struct.unpack_from('<I',binary,at-4)[0]-0x01000000
            require(binary[pointer:pointer+len(row['name'])+1] == row['name'].encode()+b'\0','ROM-selected payload name mismatch')
            require(m['full_sd_files'][row['name']]['sha256'] == row['sha256'],'Payload/SD closure mismatch')
        props = {n:v[0] for n,v in tokens((sd/'PN18.DTB').read_bytes())[1].items()}
        require(props[BANK_NODE+'/reg'] == struct.pack('>II',BANK_BASE,m['whole_voice']['span']) and props[BANK_NODE+'/no-map'] == b'', 'Voice bank DT reservation mismatch')
        base = cpio_read((sd/'PN04FS.BIN').read_bytes())
        import gzip
        base.update(cpio_read(gzip.decompress((sd/'PN18UPD.GZ').read_bytes())))
        hashes = {label:hashlib.sha256(base[name][1]).hexdigest() for label,name in ROOTFS_PATHS.items()}
        require(hashlib.sha256(base['usr/bin/xq-coach-worker'][1]).hexdigest() == WORKER,'Frozen image worker changed')
        require(m['kernel_sha256'] == m['full_sd_files']['PN08K.BIN']['sha256'],'Frozen kernel changed')
        for line in (sd/'PN18.SHA').read_text().splitlines():
            digest,name=line.split('  ',1); require(m['full_sd_files'][name]['sha256'] == digest,'PN18.SHA closure')
        p.copy(pn18/'manifest.json',p.delivery/'EVIDENCE/pn18-build.json')
        p.copy(pn18/'README.txt',p.delivery/'EVIDENCE/loader-readme.txt')
        component_proofs = {}
        if not a.sd_only_self_test:
            require(all([a.gui_build,a.speech_build,a.engine_kit,a.asr_kit,a.source_bindings]),'Four software builds/kits plus bindings required')
            bindings_path = workspace_path(a.source_bindings); p.bind(bindings_path)
            bindings = json.loads(bindings_path.read_text()); envelope = bindings if 'rows' not in bindings else {}
            frozen = envelope.get('frozen_source_snapshots',{})
            # Export/rebuild sequentially: each proof binds precisely the final rootfs ELF.
            component_proofs['gui'] = p.software_build('gui',workspace_path(a.gui_build),hashes['gui'],frozen.get('gui'))
            component_proofs['speech'] = p.software_build('speech',workspace_path(a.speech_build),hashes['speech'],frozen.get('speech'))
            component_proofs['asr'] = p.asr_kit(workspace_path(a.asr_kit),hashes['asr'])
            component_proofs['engine'] = p.engine_kit(workspace_path(a.engine_kit),hashes['engine'])
            for name,row in envelope.get('attachments',{}).items():
                safe_name(name)
                require(name.startswith(('EVIDENCE/','AUDITION/')), 'Only evidence/audition attachments allowed')
                attached = workspace_path(Path(row['file']))
                require(p.bind(attached)['sha256'] == row['sha256'], 'Bound attachment changed: '+name)
                p.copy(attached,p.delivery/name)
            old_path = Path(envelope['pn08_bindings']) if envelope else bindings_path
            p.bind(old_path); old = json.loads(old_path.read_text()); require(len(old['rows']) == 295 and not old['unresolved'],'All original295 required')
            legacy=[]; sd_objects={r['sha256']:'SD_ROOT/'+n for n,r in m['full_sd_files'].items()}
            for row in old['rows']:
                data,origin=p.source_bytes(Path(row['verified_path']),row['sha256'])
                archived=sd_objects.get(row['sha256']) or p.object(data,row['sha256'])
                legacy.append(dict(original_path=row['original_path'],sha256=row['sha256'],archived=archived,origin=origin))
            p.record(p.delivery/'SOURCE/legacy-pn08/original295.json',dict(status='ALL295_ORIGINAL_HASHES_ARCHIVED_OR_IDENTICAL_SD_MEMBER',rows=legacy))
            worker=workspace_path(a.worker_directory or Path(envelope['worker_directory']))
            require(p.bind(worker/'xq-coach-worker-stripped')['sha256'] == WORKER,'Exact retained r14 worker required')
            before=(worker/'source-before.sha256').read_bytes(); require(before == (worker/'source-after.sha256').read_bytes(),'Retained image worker input drift')
            p.bind(worker/'source-before.sha256');p.bind(worker/'source-after.sha256')
            wr=[]
            for digest,path in parse_sources(before):
                data,origin=p.source_bytes(path,digest);wr.append(dict(original_path=str(path),sha256=digest,archived=p.object(data,digest),origin=origin))
            p.record(p.delivery/'SOURCE/image-worker/compiled-sources.json',dict(binary_sha256=WORKER,rows=wr))
            for name in ['source-before.sha256','source-after.sha256','runtime-config.txt']:
                p.copy(worker/name,p.delivery/'SOURCE/image-worker'/name)
            for key in ['worker_proof','loader_proof']:
                if key in envelope:
                    evidence=Path(envelope[key]);document=json.loads(evidence.read_text())
                    if key == 'loader_proof':
                        require(document['status'] == 'PN18_EIGHT_PAYLOAD_HOST_SAME_GCC16_RV32_DTB_PASS_NOT_BOARD' and
                                document['candidate_manifest']['sha256'] == file_identity(pn18/'manifest.json')['sha256'],
                                'Loader proof must bind this exact PN18 build')
                    p.copy(evidence,p.delivery/'EVIDENCE'/(key+'.json'))
        # Archive the complete new loader and wrapper source without model duplication.
        for file in (pn18/'support').rglob('*'):
            if file.is_file(): p.copy(file,p.delivery/'SOURCE/loader/support'/file.relative_to(pn18/'support'))
        for name in ['scripts/prepare_picture_pn18.py','scripts/package_picture_pn18.py','scripts/check_xinyi_pn18_overlay.py',
                     'scripts/build_xinyi_cpu60_loader.ps1','scripts/riscv_toolchain.ps1','scripts/prepare_xinyi_cpu60_kit.py',
                     'scripts/prepare_picture_candidate.py','scripts/picture_workspace.py','scripts/build_cpu80_conv_sd.py']:
            p.copy(ROOT/name,p.delivery/'SOURCE/loader/repo'/name)
        readme = ('完整SD文件位于 SD_ROOT/，复制时保留原卡已有文件。ROM console 输入 xqboot 后，\n'
            '从 xqmodel.bin + xiangqi.bin 启动 PN18 Linux 和象棋程序，无需PC提供模型或语音服务。\n'
            'PN15XQ.BIN 是原PN15发布包入口副本；写卡前仍应另备份实际卡上的xiangqi.bin。\n'
            'P18VOICE.BIN 由新loader校验CRC并载入固定RAM；DTB精确保留no-map内存。\n'
            '请勿向已运行且未保留该区域的Linux直接加载大语音库。\n'
            'SOURCE/ 保存准确绑定的源码和独立重建证明；SOFTWARE/ 保存对应4个ELF。\n'
            '本封装过程未访问硬件/SD/Flash，不证明新的独立启动或完整音频延迟已通过。\n')
        if a.sd_only_self_test: readme='UNSELECTED SD-ONLY PLUMBING SELF-TEST; NOT A FINAL RELEASE.\n'+readme
        (p.delivery/'README.txt').write_text(readme,encoding='utf-8')
        require(all(file_identity(Path(name)) == info for name,info in p.inputs.items()),'Input drift during packaging')
        files={f.relative_to(p.delivery).as_posix():file_identity(f) for f in p.delivery.rglob('*') if f.is_file()}
        summary=dict(schema='picture-pn18-full-sd/1',status='PN18_SD_ONLY_UNSELECTED_SELF_TEST' if a.sd_only_self_test else
            'PN18_FULL_SD_FOUR_SOURCE_REBUILDS_AND_MEMBER_CLOSURE_PASS_NOT_INSTALLED',
            standalone_sd_contents=True,source_rebuilds_complete=not a.sd_only_self_test,hardware_used=False,sd_written=False,
            sd_member_count=21,rom_command='xqboot',rom_entry='xqmodel.bin + xiangqi.bin -> PN18 eight payloads',
            selected_software_sha256=hashes,component_proofs=component_proofs,files=files,
            input_files=p.inputs,commands=p.commands,physical_audio_1000ms_pass=False,standalone_boot_tested=False)
        p.record(p.delivery/'manifest.json',summary)
        (p.delivery/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+name+'\n' for name,row in sorted(files.items()))+
            file_identity(p.delivery/'manifest.json')['sha256']+'  manifest.json\n',encoding='ascii')
        archive=out/('pn18-sd-only-unselected-self-test.zip' if a.sd_only_self_test else a.archive_name)
        allfiles={f.relative_to(p.delivery).as_posix():file_identity(f) for f in p.delivery.rglob('*') if f.is_file()}
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for name in sorted(allfiles):
                safe_name(name); mode=zipfile.ZIP_STORED if name.endswith(('.zip','.xz','.gz')) else zipfile.ZIP_DEFLATED
                z.write(p.delivery/name,name,compress_type=mode)
        with zipfile.ZipFile(archive) as z:
            require(set(z.namelist()) == set(allfiles) and len(z.namelist()) == len(allfiles),'ZIP member closure')
            for name,expected in allfiles.items():
                sha=hashlib.sha256();crc=0;size=0
                with z.open(name) as stream:
                    while data:=stream.read(1024*1024):sha.update(data);crc=zlib.crc32(data,crc);size+=len(data)
                require(dict(bytes=size,sha256=sha.hexdigest(),crc32=f'{crc:08x}') == expected,'ZIP CRC/SHA mismatch: '+name)
                require(z.getinfo(name).CRC == crc,'ZIP central CRC mismatch')
        result.update(status=summary['status'],archive_path=str(archive),archive=file_identity(archive),members=len(allfiles),
                      sd_members=21,all_member_crc_sha_pass=True,source_rebuilds_complete=not a.sd_only_self_test,
                      selected_software_sha256=hashes,component_proofs=component_proofs,commands=p.commands)
    except Exception as e:
        result['error']=repr(e);raise
    finally:p.record(out/'result.json',result)
    print(result['status'],result['archive']['sha256'],result['archive']['bytes'])


if __name__ == '__main__': main()
