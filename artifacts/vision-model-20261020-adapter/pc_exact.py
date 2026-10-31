"""Install the r08 exact PC oracle before constructing any quantized runtime.

The probe characterizes this process/platform; its result never selects a less
precise implementation. Neither training delivery nor device code is modified.
"""
import platform
import hashlib
import json
import sys
from pathlib import Path
from functools import lru_cache

from exact_mm_int64_reference import exact_mm_int64_torch

def ensure_integer_ops():
    """Resolve an exact byte-identical delivered module without editing inputs."""
    here=Path(__file__).resolve().parent;repo=here.parents[1]
    frozen=here.parent/'vision-model-20261020'
    expected=json.loads((frozen/'manifest.json').read_text(encoding='utf-8'))['files']['golden/quantization/integer_ops.py']
    expected=expected if isinstance(expected,str) else expected['sha256']
    candidates=[frozen/'golden/quantization/integer_ops.py',*sorted((repo/'build/picture-r08-20261021/delivery').rglob('integer_ops.py'))]
    for path in candidates:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:
            sys.path.insert(0,str(path.parent));return path
    raise FileNotFoundError('restore the verified r08 or original R2 integer_ops.py; never substitute a numerical backend')


@lru_cache(maxsize=1)
def characterize():
    import torch
    from probe_mm_char import probe
    result, *_ = probe(32, 32, 16, 20261020)
    return dict(python=platform.python_version(), torch=torch.__version__,
                machine=platform.machine(), capability=torch.backends.cpu.get_cpu_capability(),
                original_probe=result, golden='r08-exact-int64', int_mm_is_golden=False)


def install():
    ensure_integer_ops()
    import integer_ops
    result = characterize()
    integer_ops.exact_mm = exact_mm_int64_torch
    return result


def load_integer_runtime(*args, **kwargs):
    install()
    import integer_ops
    return integer_ops.load_integer_runtime(*args, **kwargs)
