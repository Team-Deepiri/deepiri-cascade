"""Parser for npm package.json files."""
import json
import re
from pathlib import Path
from typing import Optional


def parse_package_json(path: Path, org: str = "team-deepiri") -> dict:
    """Parse package.json and extract internal scoped dependencies.

    Includes ``@{org}/...`` (matches cascade updates) and legacy ``@deepiri/...``.
    """
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

    deps = {}
    org_scope = f"@{org}/"

    for key in ["dependencies", "devDependencies"]:
        if key in data:
            for name, version in data[key].items():
                if name.startswith(org_scope) or name.startswith("@deepiri/"):
                    deps[name] = normalize_version(version)

    return deps


def normalize_version(version: str) -> str:
    """Normalize version string for comparison."""
    if version.startswith("file:"):
        return "file:"
    if version.startswith("workspace:"):
        return "workspace:"
    if version.startswith("^") or version.startswith("~"):
        return version[1:]
    return version


def update_package_json(path: Path, package_name: str, new_version: str) -> bool:
    """Update a dependency version in package.json."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return False

    modified = False

    for key in ["dependencies", "devDependencies"]:
        if key in data and package_name in data[key]:
            old_version = data[key][package_name]
            new_spec = f"^{new_version}" if not new_version.startswith("file:") else new_version
            data[key][package_name] = new_spec
            modified = True

    if modified:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    return modified


def get_package_version(path: Path) -> Optional[str]:
    """Get the package version from package.json."""
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("version")
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def bump_package_version(path: Path, bump_type: str) -> Optional[str]:
    """Bump the package version based on bump type."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None

    current = data.get("version", "0.0.0")
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
    else:  # patch
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    data["version"] = new_version

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return new_version