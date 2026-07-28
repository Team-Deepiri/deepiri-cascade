"""Package manifest discovery for repos that contain nested projects."""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
}


@dataclass(frozen=True)
class PackageManifest:
    kind: str
    path: Path
    project_dir: Path


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIRS for part in relative.parts)


def _pyproject_kind(path: Path) -> str:
    try:
        content = path.read_text()
    except OSError:
        return "poetry"
    if "[tool.poetry.dependencies]" in content:
        return "poetry"
    if "[tool.poetry]" in content and "[project]" not in content:
        return "poetry"
    if "[project]" in content:
        return "pep621"
    return "poetry"


def iter_package_manifests(root: Path) -> Iterable[PackageManifest]:
    """Yield package manifests in root and nested package directories."""
    root = root.resolve()
    for path in root.rglob("*"):
        if not path.is_file() or _is_skipped(path, root):
            continue
        if path.name == "package.json":
            yield PackageManifest("npm", path, path.parent)
        elif path.name == "pyproject.toml":
            yield PackageManifest(_pyproject_kind(path), path, path.parent)
        elif path.name == ".gitmodules":
            yield PackageManifest("gitmodules", path, path.parent)
