"""Decode a diagnostic raw capture without changing its pixel values."""
import argparse,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'vision-model-20261020/golden/software'))
from io_images import decode_rgb565
import cv2
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path)
p.add_argument('--width',type=int,default=1280);p.add_argument('--height',type=int,default=720);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
image=decode_rgb565(a.input.read_bytes(),a.width,a.height)
assert cv2.imwrite(str(a.output),image)
print('RGB565_PREVIEW_WRITTEN')
