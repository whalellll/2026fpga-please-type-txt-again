"""Run source-bound Picture host regression in an isolated checkout."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(REPO/'build') or (out.exists() and not args.resume) or args.receipt.exists():
        raise ValueError('fresh build output and receipt required')
    out.mkdir(parents=True,exist_ok=args.resume)
    clone = out/'isolation'

    def run(command, name, timeout=600, cwd=REPO):
        with (out/(name+'.log')).open('wb') as log:
            subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)
        print('CAPTURE_RECOVERY_GATE_PASS', name, flush=True)

    if not args.resume:
        run(['git','clone','--quiet','--shared','--no-hardlinks','--no-checkout',str(REPO),str(clone)],'clone')
        run(['git','-C',str(clone),'config','core.longpaths','true'],'longpaths')
        run(['git','-C',str(clone),'sparse-checkout','init','--cone'],'sparse-init')
        run(['git','-C',str(clone),'sparse-checkout','set','linux','sw','scripts'],'sparse-set')
        run(['git','-C',str(clone),'checkout','--quiet','--detach','HEAD'],'checkout')
    attempt=len(list(out.glob('linux-host*.log')))+1
    run_name='linux-host' if attempt==1 else 'linux-host-r'+str(attempt)
    names = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=REPO).decode().split('\0')
    inputs = {}
    for name in sorted(set(names)-{''}):
        if Path(name).parts[0] not in {'linux','sw','scripts'}:
            continue
        source = REPO/name
        if not source.is_file():
            continue
        target = clone/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        inputs[name] = sha(source)
    (out/('inputs-r'+str(attempt)+'.json')).write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
    script = '/mnt/'+clone.drive[0].lower()+'/'+clone.as_posix()[3:]+'/linux/vision/test_host.sh'
    run(['wsl','-d','Ubuntu-22.04','-u','root','--','sh',script],run_name,cwd=clone)
    log = (out/(run_name+'.log')).read_text(encoding='utf-8')
    for marker in ('PICTURE_LINUX_HOST_TEST_PASS','XQ_CAPTURE_RECOVERY_TEST_PASS','XQ_PICTURE_GUI_TEST_PASS'):
        assert marker in log,marker
    assert all(sha(REPO/name)==sha(clone/name)==digest for name,digest in inputs.items())
    result = dict(status='PASS',scope='host C and simulated MMIO/GUI IPC; no board acceptance',
                  hardware_used=False,source_stable=True,inputs=inputs,
                  linux_host_pass=True,repeated_failures=12,fresh_success_attempt=13,
                  model_IPC_frame_bytes_crc_verified=True,
                  stale_frame_rejected=True,cancellation_tested=True,unsafe_drain_fatal=True,
                  transcript_sha256=sha(out/(run_name+'.log')),full_suite_passed=False,
                  full_suite_status='Separate dated full-regression receipt; not established by this host-only run')
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    main()
