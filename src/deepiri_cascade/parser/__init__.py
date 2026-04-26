from pathlib import Path
from typing import Optional

from .poetry import parse_pyproject_toml, update_pyproject_toml, get_pyproject_version, bump_pyproject_version
from .gitmodules import parse_gitmodules, update_gitmodules, get_submodule_url

__all__ = [
    "parse_pyproject_toml",
    "update_pyproject_toml",
    "get_pyproject_version",
    "bump_pyproject_version",
    "parse_gitmodules",
    "update_gitmodules",
    "get_submodule_url",
]


def bump_pyproject_version(path: Path, bump_type: str) -> Optional[str]:
    """Bump the project version in pyproject.toml."""
    from .poetry import bump_pyproject_version as _bump
    return _bump(path, bump_type)
