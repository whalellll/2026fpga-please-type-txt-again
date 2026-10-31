"""Portable paths for this checkout and its explicit private build junction.

No drive-wide permission is inferred. The publication's historical G/H policy
is retained with its archived sources; local tests use this workspace policy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def workspace_path(value):
    path = Path(value).absolute()
    resolved = path.resolve()
    allowed = resolved.is_relative_to(ROOT)
    link = ROOT / 'build/picture-e42-20261025'
    if link.is_junction() or link.is_symlink():
        allowed = allowed or resolved.is_relative_to(link.resolve())
    if not allowed:
        raise ValueError('Use this checkout or its explicit private E build junction')
    return resolved


def wsl_path(value):
    path = workspace_path(value).as_posix()
    if path[1:3] != ':/':
        raise ValueError('Expected a Windows workspace path')
    return '/mnt/' + path[0].lower() + path[2:]
