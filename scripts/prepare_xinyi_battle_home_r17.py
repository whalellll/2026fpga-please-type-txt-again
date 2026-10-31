"""Generate only r17 home pixels from the actual scalar renderer, offline."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import struct
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    a = ap.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    dirs = ['linux/xinyi_board', 'linux/xinyi', 'linux/pikafish', 'linux/pikafish/include',
            'linux/vision', 'linux/voice', 'linux/voice_ctc', 'linux/voice_speech',
            'linux/mac_accel', 'linux/picture_new', 'sw/xiangqi', 'sw/bootloader',
            'artifacts/vision-model-20261020-adapter/runtime']
    names = ['linux/xinyi/page_template_export.c', 'linux/xinyi/xinyi_product.c',
             'linux/voice/xqvoice_protocol.c', 'sw/xiangqi/xiangqi_search.c',
             'sw/xiangqi/xiangqi_pikafish_link.c']
    header_path = ROOT / 'linux/xinyi/xinyi_battle_home_template_r17.h'
    values = dict(re.findall(r'^#define (XY17_\w+) ("[^"\n]*")$',
        (ROOT / 'linux/xinyi/xinyi_battle_speedups_r17.h').read_text(encoding='utf8'), re.M))
    metric_values = dict(re.findall(r'^#define (XY19_\w+) ("[^"\n]*"|[0-9.eE+-]+)$',
        (ROOT / 'linux/xinyi/xinyi_home_metrics_r19.h').read_text(encoding='utf8'), re.M))
    metric_values.update(dict(re.findall(r'^#define (XY20_\w+) ("[^"\n]*"|[0-9.eE+-]+)$',
        (ROOT / 'linux/xinyi/xinyi_ui_copy_r20.h').read_text(encoding='utf8'), re.M)))
    assert len(metric_values) == 20
    assert {'XY17_IMAGE_SPEEDUP', 'XY17_VOICE_SPEEDUP', 'XY17_NNUE_SPEEDUP'}.issubset(values)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(status='FAILED_PRESERVED', hardware_used=False, pages=[], runs=[])
    flags = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
             '-Wno-misleading-indentation', '-D_POSIX_C_SOURCE=200809L',
             '-DXINYI_CPU_HZ=60000000', '-DXINYI_HOME_R13=1', '-DXINYI_HOME_R15=1',
             '-DXINYI_BATTLE_R17=1', '-DXINYI_GUI_DOUBLE_BUFFER=1', '-DXINYI_UI_FEEDBACK=1',
             '-DXINYI_COACH_MOVE_AUDIO=1', '-DXINYI_SCALAR_GLYPH_ORACLE',
             '-DVIDEO_FB_LINUX_MMAP', '-include', wsl_path(ROOT / 'linux/pikafish/gui1080_config.h'),
             *['-I' + wsl_path(ROOT / d) for d in dirs], *[wsl_path(ROOT / n) for n in names]]

    def run(label, command):
        with (out / (label + '.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 120 ' + shlex.join(command)],
                stdout=log, stderr=subprocess.STDOUT, timeout=135)
        assert p.returncode == 0, (label, p.returncode,
            (out / (label + '.log')).read_text(errors='replace')[-3000:])
        return (out / (label + '.log')).read_text(errors='replace')

    try:
        deps = run('dependencies', [*flags, '-MM'])
        prefix = wsl_path(ROOT) + '/'
        sources = {token[len(prefix):] for token in deps.replace('\\\n', ' ').split()
                   if token.startswith(prefix)}
        assert set(names).issubset(sources)
        sources.add('scripts/prepare_xinyi_battle_home_r17.py')
        before = {n: sha(ROOT / n) for n in sorted(sources)}
        result['source_sha256'] = before
        lines = ['/* Independent r17 home pixels, generated from the scalar renderer. */',
                 '#ifndef XINYI_BATTLE_HOME_TEMPLATE_R17_H', '#define XINYI_BATTLE_HOME_TEMPLATE_R17_H',
                 '#include "xinyi_battle_speedups_r17.h"']
        lines += ['#include "xinyi_home_metrics_r19.h"', '#include "xinyi_ui_copy_r20.h"']
        for key, literal in sorted(values.items()):
            lines += [f'_Static_assert(__builtin_strcmp({key},{literal})==0,',
                      '    "r17 home cache is stale; run prepare_xinyi_battle_home_r17.py");']
        for key, literal in sorted(metric_values.items()):
            expression = f'__builtin_strcmp({key},{literal})==0' if literal.startswith('"') else f'{key}=={literal}'
            lines += [f'_Static_assert({expression},',
                      '    "r19 metrics cache is stale; regenerate the r17 home cache");']
        for voice4 in (0, 1):
            folder = out / ('voice4' if voice4 else 'balanced24')
            folder.mkdir()
            exe = folder / 'export'
            argv = [*flags, '-DXINYI_ASR_VOICE4=' + str(voice4)]
            run(f'build-{voice4}', [*argv, '-lm', '-o', wsl_path(exe)])
            run(f'export-{voice4}', [wsl_path(exe), wsl_path(folder)])
            for page in ((0,2,3) if not voice4 else (0,)):
                path = folder / f'page-{page}.rgb565'
                words = struct.unpack('<1036800I', path.read_bytes())
                runs = []
                start = 0
                while start < len(words):
                    end = start + 1
                    while end < len(words) and words[end] == words[start]:
                        end += 1
                    runs.append((end - start, words[start]))
                    start = end
                if page==0:
                    lines += ['#if XINYI_ASR_VOICE4' if voice4 else '#if !XINYI_ASR_VOICE4']
                name='xy17_home_page' if page==0 else f'xy20_detail_page_{page}'
                lines += [f'static const xy15_run {name}[]={{']
                lines.extend(','.join('{%du,0x%08xu}' % v for v in runs[i:i+4]) + ','
                             for i in range(0, len(runs), 4))
                lines += ['};']
                if page==0:lines += ['#endif']
                result['pages'].append(dict(page=page,voice4=bool(voice4), runs=len(runs),
                    sha256=sha(path), rom_bytes=len(runs) * 8))
            if voice4:
                for page in (2,3):
                    assert (folder/f'page-{page}.rgb565').read_bytes()==(out/'balanced24'/f'page-{page}.rgb565').read_bytes()
            result['runs'].append(dict(voice4=bool(voice4), executable_sha256=sha(exe), flags=argv))
        lines += ['#endif', '']
        header = '\n'.join(lines).encode('utf8')
        assert before == {n: sha(ROOT / n) for n in before}, 'Compiled source changed'
        header_path.write_bytes(header)
        result.update(status='R17_HOME_SCALAR_SOURCE_BOUND_CACHE_GENERATED_NOT_BOARD',
                      header_sha256=hashlib.sha256(header).hexdigest(), speedup_literals=values,
                      legacy_header_sha256=sha(ROOT / 'linux/xinyi/xinyi_page_templates.h'))
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
