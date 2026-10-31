"""Project-local output containment, including WSL views of this workspace."""
import os
from pathlib import Path

WORKSPACE = Path('G:/fpga' if os.name == 'nt' else '/mnt/g/fpga').resolve()


def workspace_path(path):
    path = Path(path).resolve()
    if path == WORKSPACE or not path.is_relative_to(WORKSPACE):
        raise ValueError('Output must be beneath the project workspace: ' + str(path))
    return path


def wsl_path(path):
    path = workspace_path(path)
    if os.name != 'nt':
        return path.as_posix()
    value = path.as_posix()
    return '/mnt/' + value[0].lower() + value[2:]
