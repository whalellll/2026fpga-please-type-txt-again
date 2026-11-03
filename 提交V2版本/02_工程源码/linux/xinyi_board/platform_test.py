"""Bounded synthetic platform tests; never opens /dev/mem or real device tree.

Run in WSL Python3. Builds the real platform/camera copy/HOLD/drain code against
synthetic word-addressed MMIO. Also compiles the production platform for RV32.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def fixture(path,camera=True,split=False,nomap=True,short=False,cells=1,ranges=b"",clint=True):
    reserved=path/"reserved-memory"
    write(reserved/"#address-cells",struct.pack(">I",cells))
    write(reserved/"#size-cells",struct.pack(">I",1))
    write(reserved/"ranges",ranges)

    def node(name,base,size):
        write(reserved/name/"reg",struct.pack(">II",base,size))
        if nomap:write(reserved/name/"no-map",b"")

    if camera:
        if split:
            node("capture0@1b200000",0x1b200000,0x200000)
            node("capture1@1b400000",0x1b400000,0x200000)
            node("snapshot@1b600000",0x1b600000,0x200000)
        else:node("camera-preview@1b200000",0x1b200000,0x5ff000 if short else 0x600000)
    node("framebuffer@1b800000",0x1b800000,0x800000)
    if clint:node("clint-mmio@2000000",0x02000000,0x10000)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=ROOT/"build/xinyi-platform-20261024/r01")
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    fixtures=out/"device-tree-fixtures"
    fixture(fixtures/"covered")
    fixture(fixtures/"split",split=True)
    fixture(fixtures/"missing-no-map",nomap=False)
    fixture(fixtures/"truncated-camera",short=True)
    fixture(fixtures/"bad-cells",cells=2)
    fixture(fixtures/"bad-ranges",ranges=b"\0\0\0\0")
    fixture(fixtures/"missing-clint",clint=False)
    sources=[ROOT/p for p in ["linux/xinyi_board/platform.c","linux/xinyi_board/platform_test.c",
        "linux/vision/xq_camera.c","linux/vision/xq_camera_capture_retry.c","linux/vision/xq_picture.c",
        "linux/vision/xq_vision.c","sw/xiangqi/xiangqi_search.c","sw/xiangqi/xiangqi_pikafish_link.c",
        "sw/bootloader/crc32_fast.c"]]
    flags=["-std=c11","-D_POSIX_C_SOURCE=200809L","-DXY_PLATFORM_TEST","-O2","-Wall","-Wextra","-Werror","-pthread"]
    includes=[f"-I{ROOT/p}" for p in ["linux/xinyi_board","linux/vision","sw/xiangqi","sw/bootloader"]]
    calls=[]

    def run(name,command):
        completed=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (out/(name+".log")).write_bytes(completed.stdout)
        calls.append(dict(name=name,argv=list(map(str,command)),exit_code=completed.returncode,
                          log_sha256=hashlib.sha256(completed.stdout).hexdigest()))
        if completed.returncode:
            print(completed.stdout.decode(errors="replace"))
            raise SystemExit(completed.returncode)
        return completed.stdout.decode(errors="replace")

    run("host-build",["gcc",*flags,*includes,*sources,"-lutil","-o",out/"platform-test"])
    result=run("host-tests",[out/"platform-test",fixtures])
    assert "XINYI_PLATFORM_HOST_PASS" in result
    cc=Path("/opt/toolchain/bin/riscv32-linux-musl-gcc")
    rvflags=[f for f in flags if f!="-DXY_PLATFORM_TEST"]+["-march=rv32ima","-mabi=ilp32"]
    run("rv32-object",[cc,*rvflags,*includes,"-c",ROOT/"linux/xinyi_board/platform.c","-o",out/"platform-rv32.o"])
    receipt=dict(schema=1,status="PASS",scope="synthetic MMIO/DT/TTY host + production RV32 compile only",
        board_measurement=False,camera_capability="exclusive whole-source preview; no GUI composition",
        sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        commands=calls,markers=result.splitlines())
    (out/"platform-validation.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(result,end="")
    print("XINYI_PLATFORM_VALIDATION_PASS production_RV32_object no_real_camera_access")


if __name__=="__main__":main()
