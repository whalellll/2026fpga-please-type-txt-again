"""Collect compact source/binary hashes and successful bounded host evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/xinyi-host-20261024"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_log(name):
    raw=(OUT/name).read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig")


def main():
    required={"native-final.log":["XINYI_HOST_TEST_PASS","XINYI_FRAMEBUFFER_PASS","XINYI_HOST_BUILD_PASS"],
              "coremark-final.log":["XINYI_COREMARK_PROCESS_PASS","performance_validation_CRC"],
              "coremark-cancel-final.log":["XINYI_COREMARK_CANCEL_PASS","XINYI_COREMARK_CANCEL_RACE_PASS"],
              "rv32-final.log":["XINYI_PRODUCT_RV32_OBJECTS_AND_COREMARK_ELF_PASS","ELF32","soft-float"]}
    checks=[]
    for name,markers in required.items():
        text=read_log(name)
        assert all(m in text for m in markers),(name,markers)
        checks.append(dict(log=name,sha256=sha(OUT/name),status="PASS",markers=markers))
    upstream={}
    for name in ["linux/pikafish/xiangqi_fb_gui_1080.c","linux/pikafish/xiangqi_gui_theme.h",
                 "linux/pikafish/gui1080_config.h","linux/pikafish/xiangqi_piece_font_aa.h",
                 "linux/pikafish/xiangqi_ui_font_aa.h"]:
        expected=subprocess.check_output(["git","show","127ff9a5:"+name],cwd=ROOT)
        assert (ROOT/name).read_bytes()==expected,name
        upstream[name]=hashlib.sha256(expected).hexdigest()
    sources={str(p.relative_to(ROOT)).replace("\\","/"):sha(p)
             for p in (ROOT/"linux/xinyi").rglob("*") if p.is_file() and "__pycache__" not in str(p)}
    sources.update({"sw/coremark/"+n:sha(ROOT/"sw/coremark"/n) for n in
                    ["core_main.c","core_list_join.c","core_matrix.c","core_state.c","core_util.c","coremark.h","core_portme.c","core_portme.h"]})
    binaries={str(p.relative_to(OUT)).replace("\\","/"):sha(p) for p in
        [OUT/"native/libxinyi.so",OUT/"native/test-product",OUT/"native/test-fb",
         OUT/"coremark-host/xinyi-coremark",OUT/"coremark-host/test-process",
         OUT/"rv32/coremark/xinyi-coremark"]}
    preview=json.loads((OUT/"native/preview-smoke.json").read_text(encoding="utf-8"))
    assert preview["status"]=="PASS" and not preview["board_measurement"]
    result=dict(schema=1,status="PASS",scope="T2 host product/controller/actual GUI1080; RV32 compilation only",
        board_measurement=False,production_ready=False,upstream_gui="127ff9a5",upstream_gui_sha256=upstream,
        sources=sources,binaries=binaries,checks=checks,preview=preview,
        coremark=dict(scope="host real algorithm validation only; no CPU60 score",timer="CLOCK_MONOTONIC_RAW ns",
            formal_segments_minimum_seconds=10,performance_and_validation_crc_required=True,
            measured_line=next(x for x in read_log("coremark-final.log").splitlines() if x.startswith("HOST_ALGORITHM "))),
        pending=["V321 strict complete candidate protocol", "board GUI/main callbacks",
                 "voice_2 session/audio integration", "physical Space flow", "new bitstream board acceptance"])
    (OUT/"host-validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("XINYI_HOST_VALIDATION_RECEIPT_PASS")


if __name__=="__main__":main()
