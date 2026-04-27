from pathlib import Path
from typing import Optional

from .npm import parse_package_json, update_package_json, get_package_version, bump_package_version
from .poetry import parse_pyproject_toml, update_pyproject_toml, get_pyproject_version, bump_pyproject_version
from .gitmodules import parse_gitmodules, update_gitmodules, get_submodule_url

__all__ = [
    "parse_package_json",
    "update_package_json",
    "get_package_version",
    "bump_package_json_version",
    "parse_pyproject_toml",
    "update_pyproject_toml",
    "get_pyproject_version",
    "bump_pyproject_version",
    "parse_gitmodules",
    "update_gitmodules",
    "get_submodule_url",
]


def bump_package_json_version(path: Path, bump_type: str) -> Optional[str]:
    """Bump the package version in package.json."""
    from .npm import bump_package_version as _bump
    return _bump(path, bump_type)


def bump_pyproject_version(path: Path, bump_type: str) -> Optional[str]:
    """Bump the project version in pyproject.toml."""
    from .poetry import bump_pyproject_version as _bump
    return _bump(path, bump_type)