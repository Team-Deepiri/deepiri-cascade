"""Dependency graph discovery via GitHub API."""
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set, Optional
import tempfile
import shutil

from deepiri_pkg_version_manager.scanners.repo_scanner import (
    is_internal_dep,
    normalize_package_name,
)

from .parser import npm, poetry, gitmodules
from .parser.npm import parse_package_lock_json
from .parser.poetry import parse_poetry_lock


class Discovery:
    def __init__(self, token: str, org: str, verbose: bool = False):
        self.token = token
        self.org = org
        self.verbose = verbose
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._repo_cache: Dict[str, dict] = {}
        self._deps_cache: Dict[str, Dict] = {}

    def list_org_repos(self) -> List[dict]:
        """List all repos in the organization."""
        repos = []
        page = 1
        per_page = 100

        while True:
            url = f"https://api.github.com/orgs/{self.org}/repos"
            params = {"page": page, "per_page": per_page, "type": "all"}

            response = httpx.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            repos.extend(data)
            page += 1

        return repos

    def get_repo_default_branch(self, repo_name: str) -> str:
        """Get the default branch for a repo."""
        if repo_name in self._repo_cache:
            return self._repo_cache[repo_name].get("default_branch", "main")

        url = f"https://api.github.com/repos/{self.org}/{repo_name}"
        response = httpx.get(url, headers=self.headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            self._repo_cache[repo_name] = data
            return data.get("default_branch", "main")

        return "main"

    def fetch_file_content(self, repo_name: str, file_path: str) -> Optional[str]:
        """Fetch file content from a repo."""
        url = f"https://api.github.com/repos/{self.org}/{repo_name}/contents/{file_path}"
        response = httpx.get(url, headers=self.headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "content" in data:
                import base64
                return base64.b64decode(data["content"]).decode("utf-8")

        return None

    def get_tag_sha(self, repo_name: str, tag: str) -> Optional[str]:
        """Get the commit SHA that a tag points to.
        
        Args:
            repo_name: Repository name
            tag: Tag name (e.g., "v1.2.3")
        
        Returns:
            Commit SHA or None if not found
        """
        url = f"https://api.github.com/repos/{self.org}/{repo_name}/git/ref/tags/{tag}"
        response = httpx.get(url, headers=self.headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "object" in data and "sha" in data["object"]:
                return data["object"]["sha"]
        
        return None

    def get_tag_sha_direct(self, repo_name: str, tag: str) -> Optional[str]:
        """Get commit SHA directly from tag object.
        
        Args:
            repo_name: Repository name
            tag: Tag name (e.g., "v1.2.3")
        
        Returns:
            Commit SHA or None if not found
        """
        url = f"https://api.github.com/repos/{self.org}/{repo_name}/git/tags/{tag}"
        response = httpx.get(url, headers=self.headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "object" in data and "sha" in data["object"]:
                return data["object"]["sha"]
        
        return None

    def parse_dependencies(self, repo_name: str) -> Dict[str, str]:
        """Parse dependencies from a repo's package files."""
        if repo_name in self._deps_cache:
            return self._deps_cache[repo_name]

        deps = {}

        package_json = self.fetch_file_content(repo_name, "package.json")
        if package_json:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(package_json)
                f.flush()
                parsed = npm.parse_package_json(Path(f.name), self.org)
                for name, version in parsed.items():
                    normalized = normalize_package_name(name)
                    if is_internal_dep(normalized):
                        deps[name] = version

        pyproject_toml = self.fetch_file_content(repo_name, "pyproject.toml")
        if pyproject_toml:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
                f.write(pyproject_toml)
                f.flush()
                parsed = poetry.parse_pyproject_toml(Path(f.name))
                # is_internal_dep is npm-centric; pyproject.toml git URLs are
                # already filtered to team-deepiri by the parser regex.
                for name, dep_repo in parsed.items():
                    deps[name] = dep_repo

        poetry_lock = self.fetch_file_content(repo_name, "poetry.lock")
        if poetry_lock:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".lock", delete=False) as f:
                f.write(poetry_lock)
                f.flush()
                for name, dep_repo in parse_poetry_lock(Path(f.name)).items():
                    deps.setdefault(name, dep_repo)

        package_lock = self.fetch_file_content(repo_name, "package-lock.json")
        if package_lock:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(package_lock)
                f.flush()
                for name, resolved in parse_package_lock_json(Path(f.name), self.org).items():
                    deps.setdefault(name, resolved)

        gitmodules_content = self.fetch_file_content(repo_name, ".gitmodules")
        if gitmodules_content:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".gitmodules", delete=False) as f:
                f.write(gitmodules_content)
                f.flush()
                parsed = gitmodules.parse_gitmodules(Path(f.name))
                for submodule_path, dep_repo in parsed.items():
                    deps[submodule_path] = dep_repo

        self._deps_cache[repo_name] = deps
        return deps

    def build_dependency_graph(self, source_repo: str, source_tag: str) -> Dict[str, List[str]]:
        """
        Build a dependency graph for all repos in the org.
        
        Returns:
            Dict mapping repo_name -> list of repos that depend on it
        """
        if self.verbose:
            print(f"Fetching all repos in {self.org}...")

        all_repos = self.list_org_repos()
        repo_names = [r["name"] for r in all_repos]

        if self.verbose:
            print(f"Found {len(repo_names)} repos")

        graph = {source_repo: []}

        for repo_name in repo_names:
            if repo_name == source_repo:
                continue

            deps = self.parse_dependencies(repo_name)

            if source_repo in deps.values() or f"@{self.org}/{source_repo}" in deps:
                graph.setdefault(source_repo, []).append(repo_name)
                graph[repo_name] = []

        for repo_name in repo_names:
            if repo_name == source_repo:
                continue

            deps = self.parse_dependencies(repo_name)
            org_scope_prefix = f"@{self.org}/"
            for dep_name, dep_repo in deps.items():
                if dep_repo == source_repo:
                    continue
                if dep_name.startswith(org_scope_prefix):
                    actual_repo = dep_name[len(org_scope_prefix) :]
                    graph.setdefault(actual_repo, []).append(repo_name)
                elif dep_name.startswith("@deepiri/"):
                    actual_repo = dep_name.replace("@deepiri/", "")
                    graph.setdefault(actual_repo, []).append(repo_name)

        return graph

    def find_dependents(self, source_repo: str) -> List[str]:
        """Find all repos that depend on the source repo."""
        graph = self.build_dependency_graph(source_repo, "")
        return graph.get(source_repo, [])