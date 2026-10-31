"""Show why audio okay=0 is compatible with earlier output activity.

Use the actual speech worker and parent protocol with an explicit output mock.
No audio device, physical output or board access is involved.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import check_xinyi_speech_task as check
from picture_workspace import ROOT, workspace_path


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.output.absolute().is_relative_to(ROOT/'build'):
        parser.error('Use a fresh private build output directory')
    out = workspace_path(args.output)
    if not out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()):
        parser.error('Keep diagnostic receipts in the private E build directory')
    check.MOCK = replace_once(check.MOCK, '#include <assert.h>', '#include <assert.h>\n#include <fcntl.h>\n#include <stdio.h>')
    check.MOCK = replace_once(check.MOCK, ' *underflows=0;', r'''
 char path[1024];int n=snprintf(path,sizeof(path),"%s/output-issued.mock",directory);
 assert(n>0 && (size_t)n<sizeof(path));
 int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);
 assert(fd>=0 && write(fd,"PCM",3)==3 && !close(fd));
 *underflows=0;''')
    check.TEST = replace_once(check.TEST, 'static void initial(', r'''
static void output_issued(const char *directory){
 char path[1024],bytes[3];int n=snprintf(path,sizeof(path),"%s/output-issued.mock",directory);
 assert(n>0 && (size_t)n<sizeof(path));FILE *f=fopen(path,"rb");
 assert(f && fread(bytes,1,3,f)==3 && !memcmp(bytes,"PCM",3) && fgetc(f)==EOF && !fclose(f));
}
static void initial(''')
    check.TEST = replace_once(check.TEST,
        ' assert(t.underflows==9 && t.cleanup_confirmed && t.pid>0);',
        ' assert(t.underflows==9 && t.result_status==1 && t.cleanup_confirmed && t.pid>0);\n'
        ' output_issued(path);puts("AUDIO_STATUS_MOCK_OUTPUT_THEN_UNDERFLOW_RESULT1_IDLE_CONFIRMED_FAILED");')
    check.TEST = replace_once(check.TEST,
        ' assert(t.state==XY_SPEECH_FAILED && !t.cleanup_confirmed);\n'
        ' assert(!xy_speech_task_start(&t,argv[1],path,60,60,&b,"h9g7"));',
        ' assert(t.state==XY_SPEECH_FAILED && !t.cleanup_confirmed);\n'
        ' output_issued(path);assert(WIFEXITED(t.wait_status) && WEXITSTATUS(t.wait_status)==7);\n'
        ' puts("AUDIO_STATUS_MOCK_OUTPUT_THEN_EXIT7_UNCONFIRMED_FAILED");\n'
        ' assert(!xy_speech_task_start(&t,argv[1],path,60,60,&b,"h9g7"));')
    old = sys.argv
    sys.argv = [str(Path(check.__file__)), '--output', str(out)]
    try:
        check.main()
    finally:
        sys.argv = old
    text = (out/'process-tests.stdout').read_text(encoding='utf-8')
    assert 'AUDIO_STATUS_MOCK_OUTPUT_THEN_UNDERFLOW_RESULT1_IDLE_CONFIRMED_FAILED' in text
    assert 'AUDIO_STATUS_MOCK_OUTPUT_THEN_EXIT7_UNCONFIRMED_FAILED' in text
    record = dict(status='AUDIO_ZERO_NOT_SILENCE_TWO_REAL_PROTOCOL_CONTROLS_PASS_NOT_BOARD',
        actual_audio_or_board=False, original_speech_sources_unchanged=True,
        mock_output_then_underflow_keeps_resident_worker_failed=True,
        mock_output_then_exit7_keeps_cleanup_unconfirmed=True,
        historical_actual_audio_zero_cause='UNKNOWN_OLD_EVENT_HAS_NO_STATUS_UNDERFLOWS_WAIT_FIELDS',
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ['scripts/diagnose_xinyi_audio_status.py','scripts/check_xinyi_speech_task.py',
             'linux/xinyi_board/main.c','linux/xinyi_board/runtime.c']})
    (out/'diagnosis.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(record['status'])


if __name__ == '__main__':
    main()
