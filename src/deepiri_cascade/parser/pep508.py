"""Parser for setuptools / PEP 621 ``[project.dependencies]`` git pins."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

from .poetry import resolve_poetry_pin

RefKey = Literal["rev", "tag"]

# ``deepiri-gpu-utils @ git+https://github.com/Team-Deepiri/deepiri-gpu-utils.git@v0.2.0``
_GIT_DEP_PATTERN = re.compile(
    r"(?P<name>[a-z][a-z0-9_-]*)\s*@\s*git\+https?://github\.com/team-deepiri/"
    r"(?P<repo>[^\"'\s@]+?)\.git(?:@(?P<ref>[^\"'\s,]+))?",
    re.IGNORECASE,
)


def parse_project_dependencies(path: Path) -> dict[str, str]:
    """Extract Team-Deepiri git dependencies from ``[project.dependencies]``."""

    try:
        content = path.read_text()
    except FileNotFoundError:
        return {}

    if "[project]" not in content:
        return {}

    deps: dict[str, str] = {}
    for match in _GIT_DEP_PATTERN.finditer(content):
        name = match.group("name")
        repo = match.group("repo").removesuffix(".git")
        deps[name] = repo
    return deps


def get_dependency_ref_pin(path: Path, package_name: str) -> Optional[str]:
    """Return the current ``@ref`` suffix for a PEP 508 git dependency."""

    try:
        content = path.read_text()
    except FileNotFoundError:
        return None

    pattern = re.compile(
        rf"{re.escape(package_name)}\s*@\s*git\+https?://github\.com/team-deepiri/"
        rf"[^\"'\s@]+\.git@(?P<ref>[^\"'\s,]+)",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return None
    return match.group("ref")


def get_dependency_ref_key(path: Path, package_name: str) -> Optional[RefKey]:
    """Classify a PEP 508 git pin as semver tag or commit SHA."""

    ref = get_dependency_ref_pin(path, package_name)
    if ref is None:
        return None
    if ref.startswith("v") and ref[1:2].isdigit():
        return "tag"
    if re.fullmatch(r"[0-9a-f]{40}", ref, re.IGNORECASE):
        return "rev"
    if ref.startswith("v"):
        return "tag"
    return "rev"


def update_project_dependency(path: Path, package_name: str, new_ref: str) -> bool:
    """Update the ``@ref`` suffix for a PEP 508 git dependency."""

    try:
        content = path.read_text()
    except FileNotFoundError:
        return False

    pattern = re.compile(
        rf"({re.escape(package_name)}\s*@\s*git\+https?://github\.com/team-deepiri/"
        rf"[^\"'\s@]+\.git@)(?P<ref>[^\"'\s,]+)",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return False
    if match.group("ref") == new_ref:
        return False

    new_content = pattern.sub(rf"\g<1>{new_ref}", content, count=1)
    path.write_text(new_content)
    return True


def resolve_pep508_pin(*args, **kwargs):
    """Reuse Poetry pin-resolution rules for tag vs commit SHA pins."""

    return resolve_poetry_pin(*args, **kwargs)
