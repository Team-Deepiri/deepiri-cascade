"""Parser for Poetry pyproject.toml files."""
import re
from pathlib import Path
from typing import Callable, Literal, Optional

RefKey = Literal["rev", "tag"]


def parse_pyproject_toml(path: Path) -> dict:
    """Parse pyproject.toml and extract Deepiri dependencies."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return {}

    deps = {}

    # Poetry git dependencies use `git =`, not `url =`.
    # re.DOTALL so [^}]* crosses newlines for multi-line TOML blocks.
    deepiri_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*git\s*=\s*["\']https?://github\.com/team-deepiri/([^"\']+)["\'][^}]*\}',
        re.IGNORECASE | re.DOTALL
    )

    for match in deepiri_pattern.finditer(content):
        name = match.group(1)
        repo = match.group(2).removesuffix(".git")
        deps[name] = repo

    rev_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*rev\s*=\s*["\']([^"\']+)["\'][^}]*\}',
        re.IGNORECASE | re.DOTALL,
    )

    for match in rev_pattern.finditer(content):
        name = match.group(1)
        pin = match.group(2)
        if name not in deps:
            deps[name] = pin if pin.startswith("v") and pin[1:2].isdigit() else pin

    tag_pattern = re.compile(
        r'([a-z][a-z0-9_-]*)\s*=\s*\{[^}]*tag\s*=\s*["\']([^"\']+)["\'][^}]*\}',
        re.IGNORECASE | re.DOTALL,
    )

    for match in tag_pattern.finditer(content):
        name = match.group(1)
        pin = match.group(2)
        if name not in deps:
            deps[name] = pin if pin.startswith("v") else f"v{pin}"

    return deps


def update_pyproject_toml(
    path: Path,
    package_name: str,
    new_version: str,
    version_key: Optional[RefKey] = None,
) -> bool:
    """Update a Poetry git dependency pin (``rev`` or ``tag``)."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return False

    patterns: list[tuple[re.Pattern[str], str]] = []
    if version_key in (None, "rev"):
        patterns.append(
            (
                re.compile(
                    rf'({re.escape(package_name)}\s*=\s*\{{[^}}]*rev\s*=\s*["\'])([^"\']+)(["\'])',
                    re.IGNORECASE | re.DOTALL,
                ),
                r"\g<1>" + new_version + r"\g<3>",
            )
        )
    if version_key in (None, "tag"):
        patterns.append(
            (
                re.compile(
                    rf'({re.escape(package_name)}\s*=\s*\{{[^}}]*tag\s*=\s*["\'])([^"\']+)(["\'])',
                    re.IGNORECASE | re.DOTALL,
                ),
                r"\g<1>" + new_version + r"\g<3>",
            )
        )

    modified = False
    new_content = content
    for pattern, replacement in patterns:
        match = pattern.search(new_content)
        if match:
            current_version = match.group(2)
            if current_version == new_version:
                continue
            new_content = pattern.sub(replacement, new_content, count=1)
            modified = True
            break

    if modified:
        path.write_text(new_content)

    return modified


def get_dependency_ref_key(path: Path, package_name: str) -> Optional[str]:
    """Return whether a Poetry git dependency is pinned with rev or tag."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return None

    pattern = re.compile(
        rf'{re.escape(package_name)}\s*=\s*\{{(?P<body>[^}}]*)\}}',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        return None

    body = match.group("body")
    if re.search(r'\brev\s*=', body, re.IGNORECASE):
        return "rev"
    if re.search(r'\btag\s*=', body, re.IGNORECASE):
        return "tag"
    return None


def resolve_poetry_pin(
    ref_key: Optional[RefKey],
    trigger: str,
    target_ref: str,
    *,
    dep_repo: str,
    source_repo: Optional[str] = None,
    source_sha: Optional[str] = None,
    resolve_tag_sha: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Optional[str]:
    """Choose the ``rev`` or ``tag`` value to write for a Poetry git dependency.

    * **tag**-pinned consumers on a **tag** release → write the semver tag (``vX.Y.Z``).
    * **rev**-pinned consumers on a **tag** release → write the peeled commit SHA.
    * **rev**-pinned consumers on a **push** → write the commit SHA.
    * **tag**-pinned consumers on a **push** → skip (no semver release yet).
    """
    from ..triggers import is_commit_sha

    if ref_key == "tag":
        if trigger == "push":
            return None
        if target_ref.startswith("v"):
            return target_ref
        return None

    if ref_key == "rev":
        if is_commit_sha(target_ref):
            return target_ref
        if dep_repo == source_repo and source_sha:
            return source_sha
        if target_ref.startswith("v") and resolve_tag_sha:
            return resolve_tag_sha(dep_repo, target_ref)
        return None

    if is_commit_sha(target_ref):
        return target_ref
    if dep_repo == source_repo and source_sha:
        return source_sha
    if trigger == "tag" and target_ref.startswith("v"):
        return target_ref
    if trigger == "tag" and target_ref.startswith("v") and resolve_tag_sha:
        return resolve_tag_sha(dep_repo, target_ref)
    if trigger == "push" and dep_repo == source_repo and source_sha:
        return source_sha
    return None


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


def parse_poetry_lock(path: Path) -> dict:
    """Parse poetry.lock and extract Deepiri git-sourced dependencies.

    Returns a dict of {python_package_name: github_repo_name}.
    """
    try:
        content = path.read_text()
    except FileNotFoundError:
        return {}

    deps = {}

    package_block_pattern = re.compile(
        r'\[\[package\]\](.*?)(?=\[\[package\]\]|\Z)',
        re.DOTALL
    )
    name_pattern = re.compile(r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
    source_url_pattern = re.compile(
        r'\[package\.source\].*?url\s*=\s*["\']https?://github\.com/team-deepiri/([^"\']+)["\']',
        re.DOTALL
    )

    for block_match in package_block_pattern.finditer(content):
        block = block_match.group(1)
        name_match = name_pattern.search(block)
        url_match = source_url_pattern.search(block)
        if name_match and url_match:
            name = name_match.group(1)
            repo = url_match.group(1).removesuffix(".git")
            deps[name] = repo

    return deps


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
