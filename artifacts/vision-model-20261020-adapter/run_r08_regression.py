"""Run functional Windows/Linux suites in an isolated clone; preserve releases."""
import hashlib
import argparse
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / 'build/picture-r08-20261021/regression-r01'
TARGET = OUT / 'isolation'
EVIDENCE = REPO / 'docs/validation/picture-r08-offline-20261021'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_bounded(command, log, timeout, cwd):
    with log.open('wb') as stream:
        env = dict(os.environ)
        env['CPU_TOOLCHAIN'] = 'D:/cpu-tools/v35-gcc16-build/native'
        env['PATH'] = 'D:/cpu-tools/v35-gcc16-build/native/bin;D:/LJL/WORK/msys64/ucrt64/bin;' + env['PATH']
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, cwd=cwd, env=env)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=30)
            raise
    if code:
        raise RuntimeError(f'exit {code}; inspect {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-after-environment-failure', action='store_true')
    parser.add_argument('--continue-after-lto-blocker', action='store_true')
    parser.add_argument('--resume-after-soc', action='store_true')
    parser.add_argument('--resume-camera-only', action='store_true')
    args = parser.parse_args()
    if args.resume_after_soc or args.resume_camera_only:
        args.continue_after_lto_blocker=True
    if args.continue_after_lto_blocker:
        if not (OUT / 'windows-lto-failure.log').exists():
            assert 'LTO support has not been enabled' in (OUT / 'windows.log').read_text(encoding='utf-8', errors='replace')
            shutil.copyfile(OUT / 'windows.log', OUT / 'windows-lto-failure.log')
        else:
            index=len(list(OUT.glob('windows-remaining-failure*.log')))+1
            shutil.copyfile(OUT / 'windows.log',OUT / f'windows-remaining-failure-{index:02d}.log')
        if not (OUT / 'inputs-before-gui-retake-fix.json').exists():
            shutil.copyfile(OUT / 'inputs.json', OUT / 'inputs-before-gui-retake-fix.json')
        old_inputs = json.loads((OUT / 'inputs.json').read_text(encoding='utf-8'))
        for group in old_inputs.values():
            for name in group:
                if sha(REPO / name) != sha(TARGET / name):
                    shutil.copyfile(REPO / name, TARGET / name)
    elif args.resume_after_environment_failure:
        assert (OUT / 'inputs.json').is_file()
        index = len(list(OUT.glob('windows-environment-failure*.log'))) + 1
        shutil.copyfile(OUT / 'windows.log', OUT / f'windows-environment-failure-{index:02d}.log')
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-hardlinks', '--no-checkout',
                        str(REPO), str(TARGET)], check=True, timeout=180)
        subprocess.run(['git', '-C', str(TARGET), 'config', 'core.longpaths', 'true'], check=True)
        subprocess.run(['git', '-C', str(TARGET), 'checkout', '--quiet', '--detach', 'HEAD'], check=True, timeout=180)
        changed = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only', '-z'], cwd=REPO)
        extra = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=REPO)
        for name in set((changed + extra).decode().split('\0')) - {''}:
            if Path(name).parts[0] not in {'rtl', 'sw', 'ip', 'pds', 'scripts', 'sim', 'config', 'linux'}:
                continue
            src = REPO / name
            assert src.is_file(), name
            dest = TARGET / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        shutil.copyfile(REPO / 'pds/bootrom.hex', TARGET / 'pds/bootrom.hex')
    old = json.loads((REPO / 'docs/validation/picture-p21-runtime-20261020/regression-r06.json').read_text(encoding='utf-8'))
    groups = {key: {name: sha(REPO / name) for name in old[key]} for key in (
        'source_files_sha256', 'test_files_sha256', 'linux_files_sha256')}
    for group in groups.values():
        assert all(sha(TARGET / name) == digest for name, digest in group.items())
    if args.resume_after_environment_failure:
        assert groups == json.loads((OUT / 'inputs.json').read_text(encoding='utf-8'))
    else:
        (OUT / 'inputs.json').write_text(json.dumps(groups, indent=2) + '\n', encoding='utf-8')
    print('R08_REGRESSION_ISOLATED', *map(len, groups.values()), flush=True)
    (TARGET/'build').mkdir(exist_ok=True)
    if args.resume_camera_only:
        text=(OUT/'windows.log').read_text(encoding='utf-8',errors='replace')
        assert 'FileNotFoundError' in text and 'CAMERA_SD_PNG_ALL_PIXELS_COLOR_ENDIAN_ROW_CRC_PASS' in text
        shutil.copyfile(OUT/'windows.log',OUT/'windows-through-camera.log')
    if args.resume_after_soc:
        text=(OUT / 'windows.log').read_text(encoding='utf-8',errors='replace')
        assert 'SOC_SOC_TESTS_PASS' in text and 'Missing bootloader map' in text
        shutil.copyfile(OUT / 'windows.log',OUT / 'windows-through-soc.log')
        # Reuse an exact-input historical boot build for the speaker's existing
        # SkipBootloaderBuild checks. This does NOT satisfy the failed LTO gate.
        previous=Path('D:/picture-p21-regression-20261020-r06/artifacts')
        manifest=json.loads((previous / 'bootloader.build.json').read_text(encoding='utf-8'))
        assert all(sha(REPO/name)==digest for name,digest in manifest['build_inputs'].items())
        assert all(sha(previous/manifest[key])==manifest[key+'_sha256'] for key in ('elf','binary'))
        reused={}
        for name in ('bootloader.map','bootloader.bin','bootloader.elf','bootloader.build.json'):
            shutil.copyfile(previous/name,TARGET/'artifacts'/name)
            reused[name]=sha(previous/name)
        (OUT/'reused-boot-build.json').write_text(json.dumps(dict(source='Historical r06 isolated build',
             exact_current_boot_inputs_match=True,full_lto_gate_still_failed=True,files=reused),indent=2)+'\n',encoding='utf-8')
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(TARGET / 'scripts/run_all_tests.ps1'), '-PythonPath', str(REPO / 'build/picture-tools/python3144/python.exe'),
               '-PdsRoot', 'D:/LJL/WORK/pango/PDS_2022.2-SP6.4',
               '-ToolchainBin', 'D:/cpu-tools/v35-gcc16-build/native/bin',
               '-HostGccPath', 'D:/LJL/WORK/msys64/ucrt64/bin/gcc.exe']
    marker = 'SOC_ALL_TESTS_PASS'
    if args.continue_after_lto_blocker:
        marker = 'R08_REMAINING_FUNCTIONAL_TESTS_PASS'
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(HERE / 'continue_r08_functional.ps1'), '-Repository', str(TARGET),
                   '-PythonPath', str(REPO / 'build/picture-tools/python3144/python.exe')]
        if args.resume_after_soc:command+=['-AfterSoc']
        if args.resume_camera_only:command+=['-CameraOnly']
    run_bounded(command, OUT / 'windows.log', 1800, TARGET)
    assert (OUT / 'windows.log').read_text(encoding='utf-8-sig', errors='replace').splitlines().count(marker) == 1
    print('R08_WINDOWS_FUNCTIONAL_COMPLETE', marker, flush=True)
    wsl_script = '/mnt/' + TARGET.drive[0].lower() + '/' + (TARGET / 'linux/vision/test_host.sh').as_posix()[3:]
    run_bounded(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', wsl_script], OUT / 'linux.log', 300, TARGET)
    assert 'PICTURE_LINUX_HOST_TEST_PASS' in (OUT / 'linux.log').read_text(encoding='utf-8', errors='replace')
    for group in groups.values():
        assert all(sha(REPO / name) == sha(TARGET / name) == digest for name, digest in group.items())
    result = dict(schema_version=1, status='PARTIAL_TOOLCHAIN_BLOCKED' if args.continue_after_lto_blocker else 'PASS',
                  scope='Isolated functional suites; mandatory full entry point LTO gate retained; no PDS/PnR/hardware',
                  full_suite_passed=not args.continue_after_lto_blocker,
                  blocker='Installed GCC 16.2.0 has --disable-lto; mandatory bootloader LTO build fails' if args.continue_after_lto_blocker else None,
                  windows_marker=marker, linux_marker='PICTURE_LINUX_HOST_TEST_PASS',
                  source_stable_after_execution=True, **groups)
    result['transcripts'] = {}
    for name in ('windows', 'linux'):
        dest = EVIDENCE / (name + '-regression.txt')
        shutil.copyfile(OUT / (name + '.log'), dest)
        result['transcripts'][name] = dict(path=dest.relative_to(REPO).as_posix(), sha256=sha(dest))
    if args.continue_after_lto_blocker:
        dest=EVIDENCE / 'windows-full-lto-failure.txt'
        shutil.copyfile(OUT / 'windows-lto-failure.log', dest)
        result['transcripts']['full_lto_failure']=dict(path=dest.relative_to(REPO).as_posix(),sha256=sha(dest))
    if (OUT/'windows-through-soc.log').exists():
        for name in ('windows-through-soc.log','windows-through-camera.log','reused-boot-build.json'):
            if not (OUT/name).exists():continue
            dest=EVIDENCE/name.replace('.log','.txt')
            shutil.copyfile(OUT/name,dest)
            result['transcripts'][name]=dict(path=dest.relative_to(REPO).as_posix(),sha256=sha(dest))
    (EVIDENCE / 'regression.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('R08_REGRESSION_ARCHIVED', result['status'], flush=True)


if __name__ == '__main__':
    main()
