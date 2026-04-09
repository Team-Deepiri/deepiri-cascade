"""Parser for Poetry pyproject.toml files."""
import re
from pathlib import Path
from typing import Optional


def parse_pyproject_toml(path: Path) -> dict:
    """Parse pyproject.toml and extract Deepiri dependencies."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return {}

    deps = {}

    deepiri_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*url\s*=\s*["\']https?://github\.com/team-deepiri/([^"\']+)["\'][^}]*\}',
        re.IGNORECASE
    )

    for match in deepiri_pattern.finditer(content):
        name = match.group(1)
        repo = match.group(2).removesuffix(".git")
        deps[name] = repo

    rev_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*rev\s*=\s*["\']v?([0-9.]+)["\'][^}]*\}',
        re.IGNORECASE
    )

    for match in rev_pattern.finditer(content):
        name = match.group(1)
        version = match.group(2)
        deps[name] = f"v{version}"

    tag_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*tag\s*=\s*["\']v?([0-9.]+)["\'][^}]*\}',
        re.IGNORECASE
    )

    for match in tag_pattern.finditer(content):
        name = match.group(1)
        version = match.group(2)
        deps[name] = f"v{version}"

    return deps


def update_pyproject_toml(path: Path, package_name: str, new_version: str, version_key: str = "rev") -> bool:
    """Update a dependency version in pyproject.toml."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return False

    new_version_clean = new_version.lstrip("v")

    patterns = [
        (re.compile(rf'({re.escape(package_name)}\s*=\s*\{{[^}}]*rev\s*=\s*["\'])v?[0-9.]+(["\'])', re.IGNORECASE),
         rf'\g<1>{new_version_clean}\g<2>'),
        (re.compile(rf'({re.escape(package_name)}\s*=\s*\{{[^}}]*tag\s*=\s*["\'])v?[0-9.]+(["\'])', re.IGNORECASE),
         rf'\g<1>{new_version_clean}\g<2>'),
    ]

    modified = False
    new_content = content

    for pattern, replacement in patterns:
        if pattern.search(new_content):
            new_content = pattern.sub(replacement, new_content)
            modified = True
            break

    if modified:
        path.write_text(new_content)

    return modified


def get_pyproject_version(path: Path) -> Optional[str]:
    """Get the project version from pyproject.toml."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return None

    version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    if version_match:
        return version_match.group(1)

    return None


def bump_pyproject_version(path: Path, bump_type: str) -> Optional[str]:
    """Bump the project version in pyproject.toml."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return None

    version_match = re.search(r'(version\s*=\s*["\'])([0-9.]+)(["\'])', content)
    if not version_match:
        return None

    current = version_match.group(2)
    parts = current.split(".")
    
    while len(parts) < 3:
        parts.append("0")

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    new_content = f"{version_match.group(1)}{new_version}{version_match.group(3)}"

    content = content.replace(version_match.group(0), new_content)
    path.write_text(content)

    return new_version