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
