"""Parser for .gitmodules files."""
import re
from pathlib import Path
from typing import Optional


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

        url_match = re.search(r'url\s*=\s*(.+?)$', block, re.MULTILINE)
        if url_match:
            url = url_match.group(1).strip()
            if "team-deepiri/" in url:
                parts = url.rsplit("team-deepiri/", 1)
                repo = parts[-1].rstrip(".git")
                deps[name] = repo

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