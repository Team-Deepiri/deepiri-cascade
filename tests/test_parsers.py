"""Tests for deepiri-cascade."""
import pytest
from pathlib import Path
import tempfile
import json

from deepiri_cascade.parser import npm, poetry, gitmodules


class TestNpmParser:
    def test_parse_package_json_with_deepiri_deps(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "@deepiri/test",
                "version": "1.0.0",
                "dependencies": {
                    "@deepiri/shared-utils": "^1.2.0",
                    "express": "^4.0.0"
                },
                "devDependencies": {
                    "@deepiri/types": "^0.1.0"
                }
            }, f)
            f.flush()
            
            deps = npm.parse_package_json(Path(f.name))
            assert "@deepiri/shared-utils" in deps
            assert "@deepiri/types" in deps
            assert "express" not in deps

    def test_parse_package_json_team_deepiri_scope(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "name": "consumer",
                    "version": "1.0.0",
                    "dependencies": {
                        "@team-deepiri/deepiri-shared-utils": "^1.1.0",
                        "lodash": "^4.0.0",
                    },
                },
                f,
            )
            f.flush()
            deps = npm.parse_package_json(Path(f.name), org="team-deepiri")
            assert "@team-deepiri/deepiri-shared-utils" in deps
            assert "lodash" not in deps

    def test_update_package_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {
                    "@deepiri/shared-utils": "^1.2.0"
                }
            }, f)
            f.flush()
            
            result = npm.update_package_json(Path(f.name), "@deepiri/shared-utils", "2.0.0")
            assert result is True
            
            with open(f.name) as rf:
                data = json.load(rf)
            assert data["dependencies"]["@deepiri/shared-utils"] == "^2.0.0"

    def test_update_package_json_strips_v_prefix(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {
                    "@team-deepiri/shared-utils": "^1.0.0"
                }
            }, f)
            f.flush()

            result = npm.update_package_json(Path(f.name), "@team-deepiri/shared-utils", "v2.0.0")
            assert result is True

            with open(f.name) as rf:
                data = json.load(rf)
            assert data["dependencies"]["@team-deepiri/shared-utils"] == "^2.0.0"

    def test_update_package_json_returns_false_when_version_is_already_target(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {
                    "@deepiri/shared-utils": "^1.0.0"
                }
            }, f)
            f.flush()

            result = npm.update_package_json(Path(f.name), "@deepiri/shared-utils", "v1.0.0")
            assert result is False

    def test_update_package_json_skips_file_dependency(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {
                    "@team-deepiri/shared-utils": "file:../../shared/deepiri-shared-utils"
                }
            }, f)
            f.flush()

            result = npm.update_package_json(Path(f.name), "@team-deepiri/shared-utils", "v2.0.0")
            assert result is False

            with open(f.name) as rf:
                data = json.load(rf)
            assert data["dependencies"]["@team-deepiri/shared-utils"] == "file:../../shared/deepiri-shared-utils"

    def test_update_package_json_skips_workspace_dependency(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {
                    "@team-deepiri/shared-utils": "workspace:*"
                }
            }, f)
            f.flush()

            result = npm.update_package_json(Path(f.name), "@team-deepiri/shared-utils", "v2.0.0")
            assert result is False

    def test_bump_package_version(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test", "version": "1.2.3"}, f)
            f.flush()
            
            new_version = npm.bump_package_version(Path(f.name), "patch")
            assert new_version == "1.2.4"
            
            new_version = npm.bump_package_version(Path(f.name), "minor")
            assert new_version == "1.3.0"
            
            new_version = npm.bump_package_version(Path(f.name), "major")
            assert new_version == "2.0.0"


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

    def test_parse_gitmodules_matches_org_case_insensitively(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gitmodules", delete=False) as f:
            f.write("""
[submodule "platform-services/shared/deepiri-shared-utils"]
    path = platform-services/shared/deepiri-shared-utils
    url = git@github.com:Team-Deepiri/deepiri-shared-utils.git
""")
            f.flush()

            deps = gitmodules.parse_gitmodules(Path(f.name))
            assert deps["platform-services/shared/deepiri-shared-utils"] == "deepiri-shared-utils"

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
        assert calls[0][0] == ["git", "submodule", "update", "--init", "--recursive", "libs/deepiri-core"]
        assert calls[0][1]["cwd"] == repo
        assert calls[1][0] == ["git", "fetch", "origin", "--tags", "--force"]
        assert calls[2][0] == ["git", "checkout", "abc123"]
        assert calls[1][1]["cwd"] == submodule

    def test_update_submodule_ref_returns_false_when_fetch_fails(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        submodule = repo / "libs" / "deepiri-core"
        submodule.mkdir(parents=True)
        calls = []

        class Result:
            def __init__(self, returncode=0, stderr=""):
                self.returncode = returncode
                self.stderr = stderr

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "fetch"]:
                return Result(1, "fetch failed")
            return Result()

        monkeypatch.setattr("deepiri_cascade.parser.gitmodules.subprocess.run", fake_run)

        assert gitmodules.update_submodule_ref(repo, "libs/deepiri-core", "abc123") is False
        assert calls[1] == ["git", "fetch", "origin", "--tags", "--force"]

    def test_update_submodule_ref_returns_false_when_init_fails(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()

        class Result:
            returncode = 1
            stderr = "submodule init failed"

        def fake_run(cmd, **kwargs):
            return Result()

        monkeypatch.setattr("deepiri_cascade.parser.gitmodules.subprocess.run", fake_run)

        assert gitmodules.update_submodule_ref(repo, "libs/deepiri-core", "abc123") is False
