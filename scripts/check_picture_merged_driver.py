"""Merged copy/default checks and whole driver compilation; no device access.

The existing configured kernel is a read-only source of headers/compiler flags.
Every new source, dependency file, object and log stays in the private output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--kernel-tree', required=True)
    a = p.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    names = ['pango_mac.c','pango_mac_io32.h','pango_mac_copy_chunks.h','pango_vision_io_modes.h']
    inputs = {}
    for name in names:
        b = (ROOT/'linux/mac_accel/kernel'/name).read_bytes()
        (out/name).write_bytes(b); inputs[name] = hashlib.sha256(b).hexdigest()
    api = ROOT/'linux/mac_accel/pango_mac_uapi.h'
    dest = out/'include/uapi/linux/pango_mac.h'
    dest.parent.mkdir(parents=True); dest.write_bytes(api.read_bytes())
    inputs['pango_mac_uapi.h'] = hashlib.sha256(api.read_bytes()).hexdigest()
    rows = []

    def run(name, args, cwd=None, success=True):
        command = (['sh','-c','cd '+shlex.quote(cwd)+'\nexec '+shlex.join(args)] if cwd else args)
        r = subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
            'ulimit -c 0\nexec timeout --kill-after=5 90 '+shlex.join(command)],
            capture_output=True, timeout=110)
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        rows.append(dict(name=name, exit=r.returncode, expected_success=success))
        assert (r.returncode == 0) == success, (name,(r.stdout+r.stderr)[-2200:])
        return r.stdout

    fixture = (ROOT/'linux/mac_accel/test_io32_bulk.c').read_text()
    initializer = re.search(r'static unsigned int vision_io_mode(?:\s*=\s*[^;]+)?;',
                            (out/'pango_mac.c').read_text()).group(0)
    fixture = fixture.replace('#include "kernel/pango_mac_io32.h"',
        '#include "pango_mac_io32.h"\n#define readl readl_relaxed\n#define writel writel_relaxed\n'
        '#include "pango_vision_io_modes.h"\n'+initializer)
    fixture = fixture.replace('int main(void)\n{',
        'int main(void)\n{\n assert(vision_io_mode==1u);')
    for mode in ['bulk','unrolled']:
        text = fixture.replace('pango_mac_toio32(', 'pango_mac_toio32_'+mode+'(')
        text = text.replace('pango_mac_fromio32(', 'pango_mac_fromio32_'+mode+'(')
        source = out/(mode+'.c'); source.write_text(text,newline='\n')
        for target in ['host','rv32','sanitizer']:
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'gcc'
            flags = ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target == 'rv32' else []
            if target == 'sanitizer': flags += ['-fsanitize=address,undefined','-fno-sanitize-recover=all']
            exe = out/(mode+'-'+target)
            run(exe.name+'-build',[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,
                                  '-I'+wsl_path(out),wsl_path(source),'-o',wsl_path(exe)])
            log = run(exe.name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)])
            assert b'cases=192' in log
    # A build regression to main's implicit zero default must fail this oracle.
    mutant = out/'default-mutant.c'
    mutant.write_text(fixture.replace(initializer,'static unsigned int vision_io_mode;')
                     .replace('pango_mac_toio32(', 'pango_mac_toio32_bulk(')
                     .replace('pango_mac_fromio32(', 'pango_mac_fromio32_bulk('),newline='\n')
    run('default-mutant-build',['gcc','-std=c11','-O2','-I'+wsl_path(out),wsl_path(mutant),'-o',wsl_path(out/'default-mutant')])
    run('default-mutant',[wsl_path(out/'default-mutant')],success=False)
    record = subprocess.check_output(['wsl.exe','-d','Ubuntu-22.04','--','head','-n','1',
        a.kernel_tree+'/drivers/misc/.pango_mac.o.cmd'],timeout=20).decode()
    flags = shlex.split(record.split(' := ',1)[1])
    assert flags[-1] == 'drivers/misc/pango_mac.c' and flags[-3] == '-o'
    flags = [x for x in flags[:-4] if not x.startswith('-DPANGO_MAC_IO32_BULK')]
    flags = [('-Wp,-MMD,'+wsl_path(out/'pango_mac.d')) if x.startswith('-Wp,-MMD,') else x for x in flags]
    (out/'original-kernel-command.txt').write_text(record)
    for bulk in [0,1]:
        run('kernel-object-'+str(bulk),[flags[0],'-I'+wsl_path(out/'include'),*flags[1:],
            '-DPANGO_MAC_IO32_BULK='+str(bulk),'-c','-o',wsl_path(out/('pango_mac-'+str(bulk)+'.o')),
            wsl_path(out/'pango_mac.c')],cwd=a.kernel_tree)
    result = dict(status='MERGED_BULK_UNROLL_DEFAULT_NEGATIVE_AND_FULL_DRIVER_OBJECTS_PASS_NOT_BOARD',
        inputs_sha256=inputs, checks=rows, copied_cases_per_variant_target=192,
        hardware_used=False, kernel_link_or_boot=False, kernel_tree_modified=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
