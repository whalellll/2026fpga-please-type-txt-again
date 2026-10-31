"""Bounded synthetic resident IPC tests on verified /run tmpfs; no real models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=ROOT/"build/xinyi-coach-task-20261024/r01")
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    models=out/"synthetic-model-mode-fixtures"
    models.mkdir(exist_ok=True)
    flags=["-std=c11","-O2","-Wall","-Wextra","-Werror","-pthread"]
    includes=[f"-I{ROOT/p}" for p in ["linux/xinyi_board","linux/picture_new","linux/vision","sw/bootloader","sw/xiangqi"]]
    shared=[ROOT/"linux/picture_new/coach_protocol.c",ROOT/"sw/bootloader/crc32_fast.c"]
    calls=[]

    def run(name,command):
        completed=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        (out/(name+".log")).write_bytes(completed.stdout)
        calls.append(dict(name=name,argv=list(map(str,command)),exit_code=completed.returncode,
                          log_sha256=hashlib.sha256(completed.stdout).hexdigest()))
        if completed.returncode:
            print(completed.stdout.decode(errors="replace"))
            raise SystemExit(completed.returncode)
        return completed.stdout.decode(errors="replace")

    fake=out/"fake-coach-worker"
    test=out/"coach-task-test"
    run("host-worker-build",["gcc",*flags,*includes,ROOT/"linux/xinyi_board/coach_fake_worker.c",*shared,"-lm","-o",fake])
    run("host-client-build",["gcc",*flags,*includes,ROOT/"linux/xinyi_board/coach_task.c",ROOT/"linux/xinyi_board/coach_task_test.c",*shared,"-lm","-o",test])
    result=run("host-tests",[test,fake,models])
    assert "XINYI_COACH_HOST_PASS" in result
    clock_source=ROOT/"linux/xinyi_board/coach_clock_test.c"
    clock_test=out/"coach-task-clock-test"
    clock_flags=[*flags,"-Wl,--wrap=clock_gettime"]
    run("host-clock-build",["gcc",*clock_flags,*includes,ROOT/"linux/xinyi_board/coach_task.c",ROOT/"linux/xinyi_board/coach_task_test.c",clock_source,*shared,"-lm","-o",clock_test])
    clock_result=run("host-clock-tests",[clock_test,fake,models])
    assert "XINYI_COACH_HOST_PASS" in clock_result
    # Negative control restores only the old elapsed expression in a private
    # build copy, proving the forced boundary catches this exact regression.
    old_source=out/"coach-task-before-clock-fix.c"
    current=(ROOT/"linux/xinyi_board/coach_task.c").read_text()
    fixed="now=now_ms();\n        uint64_t elapsed=now>=t->stop_time?now-t->stop_time:0;"
    assert current.count(fixed)==1
    old_source.write_text(current.replace(fixed,"uint64_t elapsed=now-t->stop_time;"))
    negative=out/"coach-task-clock-negative"
    run("host-clock-negative-build",["gcc",*clock_flags,*includes,old_source,ROOT/"linux/xinyi_board/coach_task_test.c",clock_source,*shared,"-lm","-o",negative])
    negative_result=run("host-clock-negative-control",[negative,fake,models,"clock-negative"])
    assert "XINYI_COACH_CLOCK_NEGATIVE_CONTROL_CONFIRMED" in negative_result
    cc="/opt/toolchain/bin/riscv32-linux-musl-gcc"
    rv=[*flags,"-static","-march=rv32ima","-mabi=ilp32","-mstrict-align"]
    run("rv32-client-object",[cc,*rv,*includes,"-c",ROOT/"linux/xinyi_board/coach_task.c","-o",out/"coach-task-rv32.o"])
    run("rv32-fake-worker",[cc,*rv,*includes,ROOT/"linux/xinyi_board/coach_fake_worker.c",*shared,"-lm","-o",out/"fake-coach-worker-rv32"])
    run("rv32-test-build",[cc,*rv,*includes,ROOT/"linux/xinyi_board/coach_task.c",ROOT/"linux/xinyi_board/coach_task_test.c",*shared,"-lm","-o",out/"coach-task-test-rv32"])
    # qemu-user executes the same process/IPC tests; the child must also run
    # via qemu. Use a fixed synthetic helper template generated below.
    helper=out/"qemu-fake-worker"
    helper.write_text("#!/bin/sh\nexec /usr/bin/qemu-riscv32 "+str(out/"fake-coach-worker-rv32")+' "$@"\n')
    helper.chmod(0o700)
    # Do not nest a guest exec of qemu inside a forked qemu thread. Validate
    # each target half against the host peer; actual target Linux needs no
    # emulator. Both client and fake worker target executables are exercised.
    qemu=run("rv32-qemu-tests",["qemu-riscv32",out/"coach-task-test-rv32",fake,models])
    assert "XINYI_COACH_HOST_PASS" in qemu
    qemu_worker=run("rv32-worker-qemu-tests",[test,helper,models])
    assert "XINYI_COACH_HOST_PASS" in qemu_worker
    paths=[ROOT/p for p in ["linux/xinyi_board/coach_task.c","linux/xinyi_board/coach_task.h",
        "linux/xinyi_board/coach_fake_worker.c","linux/xinyi_board/coach_task_test.c",
        "linux/xinyi_board/coach_task_test.py","linux/xinyi_board/coach_clock_test.c","linux/picture_new/coach_protocol.c","linux/picture_new/coach_protocol.h","sw/bootloader/crc32_fast.c"]]
    receipt=dict(schema=1,status="PASS",scope="synthetic resident IPC host and RV32 qemu; not model or board measurements",
        board_measurement=False,sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        checks=result.strip().splitlines(),clock_checks=clock_result.strip().splitlines(),clock_negative_control=negative_result.strip().splitlines(),
        qemu_checks=qemu.strip().splitlines(),qemu_worker_checks=qemu_worker.strip().splitlines(),commands=calls)
    (out/"coach-task-validation.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(result,end="")
    print("XINYI_COACH_TASK_VALIDATION_PASS",out/"coach-task-validation.json")


if __name__=="__main__":main()
