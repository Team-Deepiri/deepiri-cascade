"""Wave-based cascade processor."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from rich.console import Console
from rich.table import Table

from deepiri_pkg_version_manager.scanners.repo_scanner import check_git_submodules

from .ci_logging import compute_dependency_waves
from .parser import npm, poetry, gitmodules
from .github_auth import get_token_source

console = Console()


class CascadeProcessor:
    def __init__(
        self,
        token: str,
        org: str,
        bump_type: str = "patch",
        dry_run: bool = False,
        work_dir: str = "/tmp/deepiri-cascade",
        verbose: bool = False,
    ):
        self.token = token
        self.org = org
        self.bump_type = bump_type
        self.dry_run = dry_run
        self.work_dir = Path(work_dir)
        self.verbose = verbose
        self._repo_cache: Dict[str, Path] = {}
        self._source_sha: Optional[str] = None
        self._source_repo: Optional[str] = None
        self._source_tag: Optional[str] = None

        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def run(
        self,
        dependency_graph: Dict[str, List[str]],
        source_repo: str,
        source_tag: str,
        confirm: bool = True,
    ) -> Dict:
        """Run the cascade update process."""
        self._source_repo = source_repo
        self._source_tag = source_tag
        self._source_sha = self._get_tag_sha(source_repo, source_tag)
        
        if self._source_sha:
            if self.verbose:
                console.print(f"[dim]Source tag {source_tag} points to {self._source_sha[:8] if self._source_sha else 'unknown'}[/dim]")
        else:
            console.print(f"[yellow]Warning: Could not resolve tag {source_tag}, will use tag name for submodule update[/yellow]")

        dependents = dependency_graph.get(source_repo, [])

        if not dependents:
            console.print(f"[yellow]No dependent repos found for {source_repo}[/yellow]")
            return {"updated": [], "skipped": [], "failed": []}

        waves = compute_dependency_waves(dependency_graph, source_repo)

        console.print(f"\n[cyan]Found {len(dependents)} dependent repos in {len(waves)} wave(s)[/cyan]\n")

        table = Table(title="Cascade Plan")
        table.add_column("Wave", style="cyan")
        table.add_column("Repos", style="green")

        for i, wave in enumerate(waves):
            table.add_row(str(i), ", ".join(wave) if wave else "(none)")

        console.print(table)

        if confirm and not self.dry_run:
            if not console.input("\n[yellow]Proceed with cascade update? (y/n): [/yellow]"):
                console.print("[red]Aborted[/red]")
                return {"updated": [], "skipped": [], "failed": []}

        results = {"updated": [], "skipped": [], "failed": []}

        for wave_idx, wave in enumerate(waves):
            console.print(f"\n[cyan]Processing Wave {wave_idx}...[/cyan]")

            for repo in wave:
                success = self._update_repo(repo, source_repo, source_tag)
                if success:
                    results["updated"].append(repo)
                else:
                    results["failed"].append(repo)

        return results

    def _update_repo(
        self,
        repo_name: str,
        source_repo: str,
        source_tag: str,
    ) -> bool:
        """Update a single dependent repo."""
        console.print(f"  Updating {repo_name}...")

        if self.dry_run:
            console.print(f"    [dim](dry-run) Would update {source_repo} -> {source_tag}[/dim]")
            return True

        try:
            clone_path = self._get_or_clone_repo(repo_name)
            if not clone_path:
                console.print(f"    [red]Failed to clone repo[/red]")
                return False

            updated = False

            pkg_json = clone_path / "package.json"
            if pkg_json.exists():
                pkg_name = self._find_npm_dep_name(pkg_json, source_repo)
                if pkg_name and npm.update_package_json(pkg_json, pkg_name, source_tag):
                    console.print(f"    [green]Updated package.json ({pkg_name})[/green]")
                    npm.bump_package_version(pkg_json, self.bump_type)
                    self._regenerate_npm_lock(clone_path)
                    updated = True

            pyproject = clone_path / "pyproject.toml"
            if pyproject.exists():
                deps = poetry.parse_pyproject_toml(pyproject)
                for dep_name, dep_repo in deps.items():
                    if dep_repo == source_repo:
                        if poetry.update_pyproject_toml(pyproject, dep_name, source_tag):
                            console.print(f"    [green]Updated pyproject.toml[/green]")
                            poetry.bump_pyproject_version(pyproject, self.bump_type)
                            self._regenerate_poetry_lock(clone_path)
                            updated = True

            gitmodules_file = clone_path / ".gitmodules"
            if gitmodules_file.exists():
                deps = gitmodules.parse_gitmodules(gitmodules_file)
                for submodule_path, dep_repo in deps.items():
                    if dep_repo == source_repo:
                        update_ref = self._source_sha if self._source_sha else source_tag
                        if gitmodules.update_submodule_ref(clone_path, submodule_path, update_ref):
                            console.print(f"    [green]Updated submodule {submodule_path} to {update_ref[:8] if len(update_ref) > 8 else update_ref}[/green]")
                            updated = True

            if updated:
                pr_url = self._create_pull_request(repo_name, clone_path, source_repo, source_tag)
                if pr_url:
                    console.print(f"    [green]Created PR: {pr_url}[/green]")
                else:
                    console.print(f"    [red]Failed to create PR[/red]")
                    return False

            return True

        except Exception as e:
            console.print(f"    [red]Error: {e}[/red]")
            return False

    def _find_npm_dep_name(self, pkg_json: Path, source_repo: str) -> Optional[str]:
        """Find the npm package name in package.json that maps to source_repo.

        Handles the mismatch between repo names (deepiri-shared-utils) and
        npm scoped names (@team-deepiri/shared-utils).
        """
        try:
            with open(pkg_json) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return None

        for prefix in (f"@{self.org}/", "@deepiri/"):
            for key in ("dependencies", "devDependencies"):
                if key not in data:
                    continue
                for name in data[key]:
                    if not name.startswith(prefix):
                        continue
                    base = name[len(prefix):]
                    if (base == source_repo
                            or f"deepiri-{base}" == source_repo
                            or base == source_repo.removeprefix("deepiri-")):
                        return name

        return None

    def _get_or_clone_repo(self, repo_name: str) -> Optional[Path]:
        """Get cached repo or clone it with submodules."""
        if repo_name in self._repo_cache:
            path = self._repo_cache[repo_name]
            self._git_fetch(path)
            return path

        clone_path = self.work_dir / repo_name

        url = f"https://x-access-token:{self.token}@github.com/{self.org}/{repo_name}.git"
        try:
            result = subprocess.run(
                ["git", "clone", "--recurse-submodules", "--depth", "1", url, str(clone_path)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                return None

            self._repo_cache[repo_name] = clone_path
            return clone_path

        except Exception:
            return None

    def _git_fetch(self, path: Path):
        """Fetch latest changes for cached repo."""
        try:
            subprocess.run(["git", "fetch", "--all"], cwd=path, capture_output=True, timeout=30)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=path, capture_output=True, timeout=30)
        except Exception:
            pass

    def _commit_and_push(self, repo_name: str, clone_path: Path):
        """Commit and push changes to a new branch."""
        try:
            branch_name = f"deepiri-cascade/{repo_name}/deps/{self._source_sha[:8]}" if self._source_sha else f"deepiri-cascade/{repo_name}/deps/{self._source_tag}"
            
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=clone_path,
                capture_output=True,
                timeout=30,
            )

            subprocess.run(["git", "add", "-A"], cwd=clone_path, capture_output=True)
            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=clone_path,
                capture_output=True,
                text=True,
            )
            if not result.stdout.strip():
                return None

            commit_msg = f"deps: update {self._source_repo} → {self._source_tag}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=clone_path,
                capture_output=True,
            )

            subprocess.run(
                ["git", "push", "origin", branch_name, "-f"],
                cwd=clone_path,
                capture_output=True,
                timeout=60,
            )

            return branch_name

        except Exception as e:
            console.print(f"    [red]Commit/push failed: {e}[/red]")
            return None

    def _create_pull_request(
        self,
        repo_name: str,
        clone_path: Path,
        source_repo: str,
        source_tag: str,
    ) -> Optional[str]:
        """Create a pull request with auto-merge enabled."""
        branch_name = self._commit_and_push(repo_name, clone_path)
        if not branch_name:
            return None

        default_branch = self._get_default_branch(repo_name)
        
        pr_title = f"deps: update {source_repo} → {source_tag}"
        pr_body = f"""Automated cascade update triggered by {source_repo} {source_tag} release.

This PR updates the dependency on `{source_repo}` to version `{source_tag}`.

- Updated npm/pyproject dependencies
- Updated submodule refs
- Regenerated lock files
- Bumped {self.bump_type} version

Please review and merge. Auto-merge will be enabled once CI checks pass.
"""

        url = f"https://api.github.com/repos/{self.org}/{repo_name}/pulls"
        payload = {
            "title": pr_title,
            "body": pr_body,
            "head": branch_name,
            "base": default_branch,
        }

        try:
            response = httpx.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 201:
                pr_data = response.json()
                pr_number = pr_data.get("number")
                pr_url = pr_data.get("html_url")
                
                self._enable_auto_merge(repo_name, pr_number)
                
                return pr_url
            else:
                console.print(f"    [red]PR creation failed: {response.status_code} {response.text}[/red]")
                return None
                
        except Exception as e:
            console.print(f"    [red]PR creation error: {e}[/red]")
            return None

    def _enable_auto_merge(self, repo_name: str, pr_number: int) -> bool:
        """Enable auto-merge on a pull request."""
        url = f"https://api.github.com/repos/{self.org}/{repo_name}/pulls/{pr_number}/merge"
        payload = {
            "auto_merge_method": "MERGE",
            "auto_merge_enabled": True,
        }

        try:
            response = httpx.put(url, json=payload, headers=self.headers, timeout=30)
            if response.status_code in (200, 201):
                console.print(f"    [green]Auto-merge enabled[/green]")
                return True
            else:
                console.print(f"    [yellow]Auto-merge enable failed: {response.status_code}[/yellow]")
                return False
        except Exception as e:
            console.print(f"    [yellow]Auto-merge error: {e}[/yellow]")
            return False

    def _get_default_branch(self, repo_name: str) -> str:
        """Get the default branch for a repo."""
        url = f"https://api.github.com/repos/{self.org}/{repo_name}"
        try:
            response = httpx.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("default_branch", "main")
        except Exception:
            pass
        return "main"

    def _get_tag_sha(self, repo_name: str, tag: str) -> Optional[str]:
        """Get the commit SHA that a tag points to."""
        url = f"https://api.github.com/repos/{self.org}/{repo_name}/git/ref/tags/{tag}"
        try:
            response = httpx.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "object" in data and "sha" in data["object"]:
                    return data["object"]["sha"]
        except Exception:
            pass
        return None

    def _inject_npm_auth(self, clone_path: Path):
        """Inject GitHub Packages auth token into .npmrc if needed."""
        npmrc = clone_path / ".npmrc"
        auth_line = f"//npm.pkg.github.com/:_authToken={self.token}"

        if npmrc.exists():
            content = npmrc.read_text()
            if "npm.pkg.github.com" in content and "_authToken" not in content:
                npmrc.write_text(content.rstrip("\n") + f"\n{auth_line}\n")
        else:
            npmrc.write_text(f"{auth_line}\n")

    def _regenerate_npm_lock(self, clone_path: Path):
        """Regenerate package-lock.json."""
        self._inject_npm_auth(clone_path)
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                console.print(f"    [green]Regenerated package-lock.json[/green]")
            else:
                console.print(f"    [yellow]npm install warning: {result.stderr[:200]}[/yellow]")
        except Exception as e:
            console.print(f"    [yellow]npm install error: {e}[/yellow]")

    def _regenerate_poetry_lock(self, clone_path: Path):
        """Regenerate poetry.lock."""
        try:
            result = subprocess.run(
                ["poetry", "lock", "--no-update"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0:
                console.print(f"    [green]Regenerated poetry.lock[/green]")
            else:
                console.print(f"    [yellow]poetry lock warning: {result.stderr[:200]}[/yellow]")
        except Exception as e:
            console.print(f"    [yellow]poetry lock error: {e}[/yellow]")

    def _git_fetch(self, path: Path):
        """Fetch latest changes for cached repo."""
        try:
            subprocess.run(["git", "fetch", "--all"], cwd=path, capture_output=True, timeout=30)
            subprocess.run(["git", "fetch", "--recurse-submodules", "--all"], cwd=path, capture_output=True, timeout=30)
        except Exception:
            pass