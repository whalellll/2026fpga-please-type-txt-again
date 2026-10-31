"""Stage a no-model ROI/driver RAM candidate against the exact accepted hardware.

Unmodified hardware root is audited natively. Only four known Linux/RAM build
recipe differences are allowed in the current tree; every other frozen input
must match, including all RTL/IP/PDS, CPU, clocks and ROM. No device writes.
"""
import argparse,gzip,hashlib,json,struct,subprocess,zlib
from pathlib import Path
from prepare_picture_candidate import identity,tokens

SOFTWARE_RECIPES={"scripts/build_linux_mac_kernel.ps1","scripts/build_mac_conv_stage2_kernel_candidate.ps1",
                  "scripts/build_picture_loader.ps1","scripts/build_pikafish_rv32.ps1"}
def prepare(repo,hardware,kernel,dtb,rootfs,out):
    if out.exists() or not out.resolve().is_relative_to((repo/"build").resolve()):
        raise ValueError("choose a fresh output directory strictly under build/")
    audit=subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",
                          str(hardware/"scripts/audit_project.ps1"),"-Root",str(hardware)],capture_output=True,timeout=300)
    if audit.returncode or b"SOC_PROJECT_AUDIT_PASS" not in audit.stdout:
        raise ValueError("hardware root audit failed: "+audit.stderr.decode(errors="replace")[-1000:])
    snapshot=json.loads((hardware/"artifacts/build_snapshot.json").read_text())
    differences={}
    for name,expected in snapshot["inputs"].items():
        if name.startswith("artifacts/"):continue
        actual=hashlib.sha256((repo/name).read_bytes()).hexdigest()
        if actual!=expected:
            if name not in SOFTWARE_RECIPES:raise ValueError("frozen hardware input differs: "+name)
            differences[name]={"frozen_sha256":expected,"software_candidate_sha256":actual}
    sbit=identity(hardware/"artifacts/soc_top.sbit")
    if sbit["sha256"]!="e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45":
        raise ValueError("unexpected hardware candidate")
    out.mkdir(parents=True)
    raw=rootfs.read_bytes()
    if raw[:6]!=b"070701" or len(raw)>0x1000000:raise ValueError("invalid raw initrd")
    packed=gzip.compress(raw,compresslevel=6,mtime=0)
    (out/"brfs2.bin").write_bytes(packed)
    blob=bytearray(dtb.read_bytes());h,props,_=tokens(blob)
    if props["/soc/mac-accel@1fe10000/reg"][0]!=struct.pack(">II",0x1fe10000,0x200):
        raise ValueError("Stage A MMIO aperture missing")
    if len(props["/soc/mac-accel@1fe10000/memory-region"][0])!=8:
        raise ValueError("Stage A model reservation binding missing")
    if props["/reserved-memory/camera-capture@1b800000/reg"][0]!=struct.pack(">II",0x1b800000,0x400000):
        raise ValueError("background reservation missing")
    struct.pack_into(">I",blob,h[2]+props["/chosen/linux,initrd-end"][1],0x03000000+len(packed))
    (out/"br.dtb").write_bytes(blob)
    files={"brfw.bin":repo/"linux/boot/fw_jump.bin","Image":kernel,"brfs2.bin":out/"brfs2.bin",
           "br.dtb":out/"br.dtb","pikafish.pff":repo/"linux/boot/pikafish.pff","pikafish.atk":repo/"linux/boot/pikafish.atk"}
    manifest={"schema_version":1,"scope":"No-model ROI preview + shared-driver RAM candidate; NOT BoardRelease",
        "board_validated":False,"sd_written":False,"uart_kernel":True,"fixed_sbit_sha256":sbit["sha256"],
        "hardware_root":str(hardware),"hardware_run_id":snapshot["run_id"],
        "hardware_audit_stdout_sha256":hashlib.sha256(audit.stdout).hexdigest(),
        "software_recipe_differences":differences,"files":{name:identity(path) for name,path in files.items()}}
    for item in manifest["files"].values():
        item["path"]=str(Path(item["path"]).resolve())
    (out/"sd_contract.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    text="/* Generated RAM-only candidate contract. */\n"
    for prefix,name in (("PICTURE_KERNEL","Image"),("PICTURE_INITRD","brfs2.bin"),("PICTURE_DTB","br.dtb")):
        v=manifest["files"][name]
        text+=f'#define {prefix}_BYTES {v["bytes"]}u\n#define {prefix}_CRC 0x{v["crc32"]}u\n'
    (out/"picture_payloads.h").write_text(text,encoding="ascii")
    print("PICTURE_ROI_RAM_CANDIDATE_PREPARED",len(differences),"software recipe differences; hardware unchanged")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("hardware","kernel","dtb","rootfs","output"):p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args();prepare(Path(__file__).resolve().parent.parent,a.hardware,a.kernel,a.dtb,a.rootfs,a.output)
