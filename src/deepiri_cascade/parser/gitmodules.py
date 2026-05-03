"""Parser for .gitmodules files."""
from dataclasses import dataclass
import re
import subprocess
from pathlib import Path
from typing import Optional


@dataclass
class SubmoduleUpdateResult:
    success: bool
    step: str = ""
    message: str = ""


def parse_gitmodules(path: Path) -> dict:
    """Parse .gitmodules and extract Deepiri submodules."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return {}

    deps = {}

    submodule_pattern = re.compile(
        r'\[submodule\s+"([^"]+)"\](.*?)(?=\[submodule|\Z)',
        re.DOTALL
    )

    for match in submodule_pattern.finditer(content):
        name = match.group(1)
        block = match.group(2)

        path_match = re.search(r'path\s*=\s*(.+?)$', block, re.MULTILINE)
        url_match = re.search(r'url\s*=\s*(.+?)$', block, re.MULTILINE)
        if url_match:
            url = url_match.group(1).strip()
            repo_match = re.search(r'team-deepiri[/:]([^/]+?)(?:\.git)?$', url, re.IGNORECASE)
            if repo_match:
                repo = repo_match.group(1)
                submodule_path = path_match.group(1).strip() if path_match else name
                deps[submodule_path] = repo

    return deps


def update_gitmodules(path: Path, submodule_name: str, new_url: str) -> bool:
    """Update a submodule URL in .gitmodules."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return False

    pattern = re.compile(
        rf'(\[submodule\s+"{re.escape(submodule_name)}"\](.*?)(?:url\s*=\s*).+?)',
        re.DOTALL
    )

    def replace_url(m):
        block = m.group(1)
        block = re.sub(r'url\s*=\s*.+', f'url = {new_url}', block)
        return block

    if pattern.search(content):
        content = pattern.sub(replace_url, content)
        path.write_text(content)
        return True

    return False


def get_submodule_url(path: Path, submodule_name: str) -> Optional[str]:
    """Get the URL for a specific submodule."""
    deps = parse_gitmodules(path)
    return deps.get(submodule_name)


def update_submodule_ref(repo_path: Path, submodule_path: str, new_ref: str) -> bool:
    """Update a submodule to point to a new ref (tag/branch/commit).
    
    Args:
        repo_path: Path to the parent repo
        submodule_path: Relative path to the submodule (e.g., "libs/deepiri-shared")
        new_ref: The new ref to checkout (tag, branch, or commit SHA)
    
    Returns:
        True if update was successful, False otherwise
    """
    return update_submodule_ref_result(repo_path, submodule_path, new_ref).success


def update_submodule_ref_result(
    repo_path: Path,
    submodule_path: str,
    new_ref: str,
) -> SubmoduleUpdateResult:
    """Update a submodule and return details when a git step fails."""
    try:
        sync = subprocess.run(
            ["git", "submodule", "sync", "--recursive", submodule_path],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if sync.returncode != 0:
            return SubmoduleUpdateResult(False, "submodule sync", sync.stderr.strip())

        init = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive", submodule_path],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if init.returncode != 0:
            return SubmoduleUpdateResult(False, "submodule init", init.stderr.strip())

        submodule_full_path = repo_path / submodule_path
        if not submodule_full_path.exists():
            return SubmoduleUpdateResult(False, "submodule path", f"{submodule_path} does not exist after init")

        fetch = subprocess.run(
            ["git", "fetch", "origin", "--tags", "--force"],
            cwd=submodule_full_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if fetch.returncode != 0:
            return SubmoduleUpdateResult(False, "submodule fetch", fetch.stderr.strip())

        result = subprocess.run(
            ["git", "checkout", new_ref],
            cwd=submodule_full_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            if "did not match" in result.stderr or "failed" in result.stderr:
                result = subprocess.run(
                    ["git", "checkout", "-f", new_ref],
                    cwd=submodule_full_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    return SubmoduleUpdateResult(False, "submodule checkout", result.stderr.strip())
            else:
                return SubmoduleUpdateResult(False, "submodule checkout", result.stderr.strip())

        return SubmoduleUpdateResult(True)

    except subprocess.TimeoutExpired as e:
        return SubmoduleUpdateResult(False, "submodule timeout", str(e))
    except Exception as e:
        return SubmoduleUpdateResult(False, "submodule exception", str(e))


def get_submodule_current_ref(repo_path: Path, submodule_path: str) -> Optional[str]:
    """Get the current ref (commit SHA) that a submodule points to."""
    submodule_full_path = repo_path / submodule_path
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=submodule_full_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:8]
    except Exception:
        pass
    
    return None
