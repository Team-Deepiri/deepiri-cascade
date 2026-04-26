"""Tests for deepiri-cascade."""
from pathlib import Path
import tempfile

from deepiri_cascade.parser import poetry, gitmodules


class TestPoetryParser:
    def test_parse_pyproject_toml_git_dep(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
[tool.poetry.dependencies]
python = "^3.11"
deepiri-shared-utils = {git = "https://github.com/team-deepiri/deepiri-shared-utils.git", rev = "v1.2.3"}
""")
            f.flush()
            
            deps = poetry.parse_pyproject_toml(Path(f.name))
            assert "deepiri-shared-utils" in deps

    def test_update_pyproject_toml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
[tool.poetry.dependencies]
python = "^3.11"
deepiri-shared-utils = {git = "https://github.com/team-deepiri/deepiri-shared-utils.git", rev = "v1.2.3"}
""")
            f.flush()
            
            result = poetry.update_pyproject_toml(Path(f.name), "deepiri-shared-utils", "v2.0.0")
            assert result is True
            
            content = Path(f.name).read_text()
            assert "2.0.0" in content

    def test_update_pyproject_toml_returns_false_when_version_is_already_target(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
[tool.poetry.dependencies]
python = "^3.11"
deepiri-shared-utils = {git = "https://github.com/team-deepiri/deepiri-shared-utils.git", rev = "v1.2.3"}
""")
            f.flush()

            result = poetry.update_pyproject_toml(Path(f.name), "deepiri-shared-utils", "v1.2.3")
            assert result is False

    def test_update_pyproject_toml_updates_sha_pinned_rev(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
[tool.poetry.dependencies]
python = "^3.11"
deepiri-gpu-utils = {git = "https://github.com/team-deepiri/deepiri-gpu-utils.git", rev = "205034c8e1452afa790ebdf835dbbef38c126b94", extras = ["torch"]}
""")
            f.flush()

            result = poetry.update_pyproject_toml(
                Path(f.name),
                "deepiri-gpu-utils",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            assert result is True

            content = Path(f.name).read_text()
            assert 'rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in content
            assert 'extras = ["torch"]' in content

    def test_get_dependency_ref_key_detects_rev_and_tag(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
[tool.poetry.dependencies]
rev-dep = {git = "https://github.com/team-deepiri/rev-dep.git", rev = "abc123"}
tag-dep = {git = "https://github.com/team-deepiri/tag-dep.git", tag = "v1.0.0"}
""")
            f.flush()

            assert poetry.get_dependency_ref_key(Path(f.name), "rev-dep") == "rev"
            assert poetry.get_dependency_ref_key(Path(f.name), "tag-dep") == "tag"


class TestGitmodulesParser:
    def test_parse_gitmodules(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gitmodules", delete=False) as f:
            f.write("""
[submodule "libs/deepiri-core"]
    path = libs/deepiri-core
    url = git@github.com:team-deepiri/deepiri-core.git
""")
            f.flush()
            
            deps = gitmodules.parse_gitmodules(Path(f.name))
            assert "libs/deepiri-core" in deps
            assert deps["libs/deepiri-core"] == "deepiri-core"

    def test_update_gitmodules(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gitmodules", delete=False) as f:
            f.write("""
[submodule "libs/deepiri-core"]
    path = libs/deepiri-core
    url = git@github.com:team-deepiri/deepiri-core.git
""")
            f.flush()
            
            result = gitmodules.update_gitmodules(
                Path(f.name),
                "libs/deepiri-core",
                "git@github.com:team-deepiri/deepiri-core-new.git"
            )
            assert result is True

    def test_update_submodule_ref_fetches_and_checkouts_ref(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        submodule = repo / "libs" / "deepiri-core"
        submodule.mkdir(parents=True)
        calls = []

        class Result:
            def __init__(self, returncode=0, stderr=""):
                self.returncode = returncode
                self.stderr = stderr

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return Result()

        monkeypatch.setattr("deepiri_cascade.parser.gitmodules.subprocess.run", fake_run)

        result = gitmodules.update_submodule_ref(repo, "libs/deepiri-core", "abc123")

        assert result is True
        assert calls[0][0] == ["git", "fetch", "origin", "--tags", "--force"]
        assert calls[1][0] == ["git", "checkout", "abc123"]
        assert calls[0][1]["cwd"] == submodule

    def test_update_submodule_ref_returns_false_when_fetch_fails(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        submodule = repo / "libs" / "deepiri-core"
        submodule.mkdir(parents=True)

        class Result:
            returncode = 1
            stderr = "fetch failed"

        def fake_run(cmd, **kwargs):
            return Result()

        monkeypatch.setattr("deepiri_cascade.parser.gitmodules.subprocess.run", fake_run)

        assert gitmodules.update_submodule_ref(repo, "libs/deepiri-core", "abc123") is False
