"""Wave-based cascade processor."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from rich.console import Console
from rich.table import Table

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

        self.work_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        dependency_graph: Dict[str, List[str]],
        source_repo: str,
        source_tag: str,
        confirm: bool = True,
    ) -> Dict:
        """Run the cascade update process."""

        dependents = dependency_graph.get(source_repo, [])

        if not dependents:
            console.print(f"[yellow]No dependent repos found for {source_repo}[/yellow]")
            return {"updated": [], "skipped": [], "failed": []}

        waves = self._compute_waves(dependency_graph, source_repo)

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

    def _compute_waves(self, graph: Dict[str, List[str]], source: str) -> List[List[str]]:
        """Compute topological waves for dependent repos."""
        dependents = graph.get(source, [])
        
        if not dependents:
            return []

        waves = []
        processed = set()
        current_wave = dependents.copy()

        while current_wave:
            waves.append(current_wave)
            processed.update(current_wave)

            next_wave = []
            for repo in current_wave:
                for dep in graph.get(repo, []):
                    if dep not in processed and dep not in next_wave:
                        next_wave.append(dep)

            current_wave = next_wave

        return waves

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
                if npm.update_package_json(pkg_json, f"@{self.org}/{source_repo}", source_tag):
                    console.print(f"    [green]Updated package.json[/green]")
                    npm.bump_package_version(pkg_json, self.bump_type)
                    updated = True

            pyproject = clone_path / "pyproject.toml"
            if pyproject.exists():
                deps = poetry.parse_pyproject_toml(pyproject)
                for dep_name, dep_repo in deps.items():
                    if dep_repo == source_repo:
                        if poetry.update_pyproject_toml(pyproject, dep_name, source_tag):
                            console.print(f"    [green]Updated pyproject.toml[/green]")
                            poetry.bump_pyproject_version(pyproject, self.bump_type)
                            updated = True

            gitmodules_file = clone_path / ".gitmodules"
            if gitmodules_file.exists():
                deps = gitmodules.parse_gitmodules(gitmodules_file)
                for submodule, dep_repo in deps.items():
                    if dep_repo == source_repo:
                        new_url = f"git@github.com:{self.org}/{source_repo}.git"
                        if gitmodules.update_gitmodules(gitmodules_file, submodule, new_url):
                            console.print(f"    [green]Updated .gitmodules[/green]")
                            updated = True

            if updated:
                self._commit_and_push(repo_name, clone_path)

            return True

        except Exception as e:
            console.print(f"    [red]Error: {e}[/red]")
            return False

    def _get_or_clone_repo(self, repo_name: str) -> Optional[Path]:
        """Get cached repo or clone it."""
        if repo_name in self._repo_cache:
            path = self._repo_cache[repo_name]
            self._git_fetch(path)
            return path

        clone_path = self.work_dir / repo_name

        url = f"https://github.com/{self.org}/{repo_name}.git"
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, str(clone_path)],
                capture_output=True,
                text=True,
                timeout=120,
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
        """Commit and push changes."""
        try:
            subprocess.run(["git", "add", "-A"], cwd=clone_path, capture_output=True)
            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=clone_path,
                capture_output=True,
                text=True,
            )
            if not result.stdout.strip():
                return

            subprocess.run(
                ["git", "commit", "-m", f"chore: cascade update {self.bump_type} version"],
                cwd=clone_path,
                capture_output=True,
            )

            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=clone_path,
                capture_output=True,
                timeout=60,
            )

            console.print(f"    [green]Committed and pushed[/green]")

        except Exception as e:
            console.print(f"    [red]Push failed: {e}[/red]")