"""Local release helpers for bumping a repo and creating its version tag."""
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .parser import npm, poetry


@dataclass(frozen=True)
class ReleaseResult:
    version: str
    tag: str
    manifest_path: Path


def _next_version(current: str, bump_type: str) -> str:
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as e:
        raise ValueError(f"Unsupported version: {current}") from e

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"


def plan_project_version(path: Path, bump_type: str) -> ReleaseResult:
    """Calculate the next release version without editing files."""
    path = path.resolve()
    package_json = path / "package.json"
    pyproject = path / "pyproject.toml"

    if pyproject.exists():
        current = poetry.get_pyproject_version(pyproject)
        if current:
            version = _next_version(current, bump_type)
            return ReleaseResult(version=version, tag=f"v{version}", manifest_path=pyproject)

    if package_json.exists():
        current = npm.get_package_version(package_json)
        if not current:
            raise ValueError(f"Could not read npm version in {package_json}")
        version = _next_version(current, bump_type)
        return ReleaseResult(version=version, tag=f"v{version}", manifest_path=package_json)

    if pyproject.exists():
        raise ValueError(f"Could not read pyproject version in {pyproject}")

    raise FileNotFoundError(f"No package.json or pyproject.toml found in {path}")


def bump_project_version(path: Path, bump_type: str) -> ReleaseResult:
    """Bump the package version in a local project directory."""
    path = path.resolve()
    package_json = path / "package.json"
    pyproject = path / "pyproject.toml"

    if pyproject.exists() and poetry.get_pyproject_version(pyproject):
        version = poetry.bump_pyproject_version(pyproject, bump_type)
        if not version:
            raise ValueError(f"Could not bump pyproject version in {pyproject}")
        return ReleaseResult(version=version, tag=f"v{version}", manifest_path=pyproject)

    if package_json.exists():
        version = npm.bump_package_version(package_json, bump_type)
        if not version:
            raise ValueError(f"Could not bump npm version in {package_json}")
        return ReleaseResult(version=version, tag=f"v{version}", manifest_path=package_json)

    if pyproject.exists():
        raise ValueError(f"Could not read pyproject version in {pyproject}")

    raise FileNotFoundError(f"No package.json or pyproject.toml found in {path}")


def ensure_clean_worktree(path: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not inspect git status")
    if result.stdout.strip():
        raise RuntimeError("Working tree must be clean before release")


def commit_release(path: Path, tag: str, manifest_path: Path) -> None:
    subprocess.run(
        ["git", "add", str(manifest_path.relative_to(path))],
        cwd=path,
        check=True,
        timeout=30,
    )
    subprocess.run(
        ["git", "commit", "-m", f"release: {tag}"],
        cwd=path,
        check=True,
        timeout=30,
    )


def create_git_tag(path: Path, tag: str, message: Optional[str] = None) -> None:
    subprocess.run(
        ["git", "tag", "-a", tag, "-m", message or tag],
        cwd=path,
        check=True,
        timeout=30,
    )


def push_release(path: Path, tag: str) -> None:
    subprocess.run(["git", "push", "origin", "HEAD"], cwd=path, check=True, timeout=60)
    subprocess.run(["git", "push", "origin", tag], cwd=path, check=True, timeout=60)
