"""Stage all six native payloads under a Picture_new prefix; no media writes."""
import argparse
from pathlib import Path
from sd_namespace import stage

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ram', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--prefix', default='PN01')
args = parser.parse_args()
result = stage(args.ram, args.out, args.prefix)
print('NATIVE_SD_NAMESPACE_STAGED prefix=' + result['deployment']['prefix'] + ' no_media_written=1')
