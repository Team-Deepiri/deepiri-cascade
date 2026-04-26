"""Tests for CascadeProcessor helpers."""
import json
import pytest
from pathlib import Path

from deepiri_cascade.cascade import CascadeProcessor


class TestFindNpmDepName:
    """Tests for CascadeProcessor._find_npm_dep_name."""

    def setup_method(self):
        self.proc = CascadeProcessor.__new__(CascadeProcessor)
        self.proc.org = "team-deepiri"

    def _write_pkg(self, tmp_path, data):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps(data))
        return pkg

    def test_finds_org_scoped_dep(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {"@team-deepiri/shared-utils": "^1.0.0"},
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result == "@team-deepiri/shared-utils"

    def test_finds_dep_in_dev_dependencies(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "devDependencies": {"@team-deepiri/shared-utils": "^1.0.0"},
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result == "@team-deepiri/shared-utils"

    def test_finds_legacy_deepiri_scope(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {"@deepiri/shared-utils": "^1.0.0"},
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result == "@deepiri/shared-utils"

    def test_returns_none_when_not_present(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {"express": "^4.0.0"},
        })
        assert self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils") is None

    def test_returns_none_for_missing_file(self, tmp_path):
        pkg = tmp_path / "nonexistent.json"
        assert self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils") is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("{invalid json")
        assert self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils") is None

    def test_matches_repo_without_deepiri_prefix(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {"@team-deepiri/some-lib": "^1.0.0"},
        })
        result = self.proc._find_npm_dep_name(pkg, "some-lib")
        assert result == "@team-deepiri/some-lib"

    def test_exact_repo_name_match(self, tmp_path):
        """When the npm scope base name already equals the repo name."""
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {"@team-deepiri/deepiri-shared-utils": "^1.0.0"},
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result == "@team-deepiri/deepiri-shared-utils"

    def test_ignores_other_org_deps(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {
                "@other-org/shared-utils": "^1.0.0",
                "@team-deepiri/shared-utils": "^2.0.0",
            },
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result == "@team-deepiri/shared-utils"


class TestCascadeRunResults:
    def test_run_records_updated_skipped_and_failed(self):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.verbose = False
        proc.dry_run = False
        proc._get_tag_sha = lambda repo, tag: "abc123"

        statuses = {
            "repo-updated": "updated",
            "repo-skipped": "skipped",
            "repo-failed": "failed",
        }
        proc._update_repo = lambda repo, source_repo, source_tag: statuses[repo]

        graph = {"source": ["repo-updated", "repo-skipped", "repo-failed"]}

        results = proc.run(graph, "source", "v1.0.0", confirm=False)

        assert results == {
            "updated": ["repo-updated"],
            "skipped": ["repo-skipped"],
            "failed": ["repo-failed"],
        }

    def test_update_repo_uses_source_sha_for_poetry_rev_dependency(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._source_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._regenerate_poetry_lock = lambda clone_path: None
        proc._create_pull_request = lambda repo_name, clone_path, source_repo, source_tag: "https://example.test/pr"

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.poetry]
name = "consumer"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
deepiri-gpu-utils = {git = "https://github.com/Team-Deepiri/deepiri-gpu-utils.git", rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", extras = ["torch"]}
""")

        result = proc._update_repo("consumer", "deepiri-gpu-utils", "v1.0.0")

        assert result == "updated"
        content = pyproject.read_text()
        assert 'rev = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' in content
        assert 'version = "0.1.1"' in content


class TestTagShaResolution:
    def _make_response(self, status_code, payload):
        class Response:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload

            def json(self):
                return self._payload

        return Response(status_code, payload)

    def test_get_tag_sha_returns_commit_sha_for_lightweight_tag(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}

        def fake_get(url, **kwargs):
            return self._make_response(200, {
                "object": {"type": "commit", "sha": "commit-sha"},
            })

        monkeypatch.setattr("deepiri_cascade.cascade.httpx.get", fake_get)

        assert proc._get_tag_sha("source", "v1.0.0") == "commit-sha"

    def test_get_tag_sha_peels_annotated_tag(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}

        def fake_get(url, **kwargs):
            if url.endswith("/git/ref/tags/v1.0.0"):
                return self._make_response(200, {
                    "object": {"type": "tag", "sha": "tag-object-sha"},
                })
            if url.endswith("/git/tags/tag-object-sha"):
                return self._make_response(200, {
                    "object": {"type": "commit", "sha": "peeled-commit-sha"},
                })
            return self._make_response(404, {})

        monkeypatch.setattr("deepiri_cascade.cascade.httpx.get", fake_get)

        assert proc._get_tag_sha("source", "v1.0.0") == "peeled-commit-sha"


class TestNpmAuthInjection:
    def test_inject_npm_auth_writes_scope_registry_and_token(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.token = "secret-token"

        proc._inject_npm_auth(tmp_path)

        content = (tmp_path / ".npmrc").read_text()
        assert "@deepiri:registry=https://npm.pkg.github.com" in content
        assert "@team-deepiri:registry=https://npm.pkg.github.com" in content
        assert "//npm.pkg.github.com/:_authToken=secret-token" in content

    def test_inject_npm_auth_replaces_old_managed_lines(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.token = "new-token"

        npmrc = tmp_path / ".npmrc"
        npmrc.write_text(
            "@deepiri:registry=https://old.example\n"
            "@team-deepiri:registry=https://old.example\n"
            "//npm.pkg.github.com/:_authToken=old-token\n"
            "save-exact=true\n"
        )

        proc._inject_npm_auth(tmp_path)

        content = npmrc.read_text()
        assert "@deepiri:registry=https://old.example" not in content
        assert "@team-deepiri:registry=https://old.example" not in content
        assert "//npm.pkg.github.com/:_authToken=old-token" not in content
        assert "save-exact=true" in content
        assert "//npm.pkg.github.com/:_authToken=new-token" in content


class TestNpmLockRegeneration:
    def test_regenerate_npm_lock_disables_workspaces_and_scripts(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.token = "secret-token"
        calls = []

        class Result:
            returncode = 0
            stderr = ""

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return Result()

        monkeypatch.setattr("deepiri_cascade.cascade.subprocess.run", fake_run)

        proc._regenerate_npm_lock(tmp_path)

        assert calls[0][0] == [
            "npm",
            "install",
            "--package-lock-only",
            "--workspaces=false",
            "--ignore-scripts",
        ]
