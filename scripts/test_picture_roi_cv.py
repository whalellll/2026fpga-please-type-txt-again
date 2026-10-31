"""Independent OpenCV4.10 pixel oracle; synthetic images only, no Torch/weights.

Usage: python -B ... <shared library> <PC dependency directory> <receipt.json>
The package's reviewed crop_piece function is extracted without its imports,
so no checkpoint/model code executes and the original package stays read-only.
"""
import ast
import ctypes as C
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,sys.argv[2])
import cv2
import numpy as np
assert cv2.__version__ == "4.10.0"
if os.name == "nt":
    dll_directory=os.add_dll_directory("D:/LJL/WORK/msys64/ucrt64/bin")
lib=C.CDLL(str(Path(sys.argv[1]).resolve()))
class Roi(C.Structure):
    _fields_=[(n,C.c_int) for n in ("x0","y0","x1","y1")]
class Box(C.Structure):
    _fields_=[(n,C.c_float) for n in ("x0","y0","x1","y1","score")]+[("class_id",C.c_uint)]
class Plan(C.Structure):
    _fields_=[(n,C.c_uint) for n in ("size","width","height","left","top")]+[(n,C.c_double) for n in ("ratio","pad_x","pad_y")]+[("roi",Roi)]
U8=C.POINTER(C.c_uint8)
lib.xqr_piece_crop.argtypes=[U8,C.POINTER(Box),U8,C.c_size_t]
lib.xqr_detector_input.argtypes=[U8,Roi,C.c_uint,U8,C.c_size_t,C.POINTER(Plan)]
lib.xqr_resize_rgb.argtypes=[U8,C.c_uint,C.c_uint,C.c_size_t,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,U8,C.c_size_t]
def ptr(a):return a.ctypes.data_as(U8)
source=Path("build/picture-training-intake-20261019/package/piece_model15.py")
tree=ast.parse(source.read_text(encoding="utf-8"))
crop=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="crop_piece")
namespace={"cv2":cv2,"np":np}
exec(compile(ast.Module(body=[crop],type_ignores=[]),str(source),"exec"),namespace)
rng=np.random.default_rng(20261019)
rgb=rng.integers(0,256,(720,1280,3),dtype=np.uint8)
records=[]
def compare(name,actual,reference):
    diff=np.abs(actual.astype(np.int16)-reference.astype(np.int16))
    record={"name":name,"bytes":actual.size,"max_error":int(diff.max()),"different_bytes":int(np.count_nonzero(diff))}
    records.append(record)
    assert np.array_equal(actual,reference),record
for side in (1,2,3,7,13,31,32,33,63,64,65,127,320,679):
    x0,y0=0,0
    sw,sh=side,min(720,side+3)
    out=np.empty((3,32,32),np.uint8)
    assert lib.xqr_resize_rgb(ptr(rgb),1280,720,3840,x0,y0,sw,sh,32,32,ptr(out),out.size)
    expected=cv2.resize(rgb[:sh,:sw],(32,32),interpolation=cv2.INTER_LINEAR).transpose(2,0,1)
    compare(f"resize-{sw}x{sh}",out,expected)
boxes=[(0,0,18,21),(1250,690,1280,720),(40.25,12.5,70.75,42.5),(490,40,600,180)]
for _ in range(60):
    x,y=rng.uniform(0,1000),rng.uniform(0,500)
    boxes.append((x,y,x+rng.uniform(.1,200),y+rng.uniform(.1,200)))
for i,coords in enumerate(boxes):
    box=Box(*coords,.8,0)
    out=np.empty((3,32,32),np.uint8)
    assert lib.xqr_piece_crop(ptr(rgb),C.byref(box),ptr(out),out.size)
    frozen=[float(getattr(box,n)) for n in ("x0","y0","x1","y1")]
    expected=namespace["crop_piece"](rgb[:,:,::-1],frozen).transpose(2,0,1)
    compare(f"original-patch-{i}",out,expected)
for size in (320,416,640):
    for r in ((490,40,1200,719),(0,0,1280,720),(1,2,32,22),(40,50,701,701)):
        roi=Roi(*r);plan=Plan();out=np.empty((3,size,size),np.uint8)
        assert lib.xqr_detector_input(ptr(rgb),roi,size,ptr(out),out.size,C.byref(plan))
        w,h=r[2]-r[0],r[3]-r[1];ratio=min(size/w,size/h,1)
        rw,rh=round(w*ratio),round(h*ratio);px,py=(size-rw)/2,(size-rh)/2
        resized=cv2.resize(rgb[r[1]:r[3],r[0]:r[2]],(rw,rh),interpolation=cv2.INTER_LINEAR)
        expected=cv2.copyMakeBorder(resized,round(py-.1),round(py+.1),round(px-.1),round(px+.1),cv2.BORDER_CONSTANT,value=(114,114,114)).transpose(2,0,1)
        compare(f"letterbox-{size}-{r}",out,expected)
        assert (plan.width,plan.height,plan.left,plan.top)==(rw,rh,round(px-.1),round(py-.1))
receipt={"status":"PASS_OPENCV_BYTE_ORACLE","scope":"Synthetic preprocessing only; no model inference, quantization or accuracy acceptance",
    "opencv":cv2.__version__,"numpy":np.__version__,"cases":records,
    "package_crop_source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
Path(sys.argv[3]).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
print("PICTURE_ROI_OPENCV_BYTES_PASS",len(records),"cases")
