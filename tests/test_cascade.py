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

    def test_ignores_file_dependency(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {
                "@team-deepiri/shared-utils": "file:../../shared/deepiri-shared-utils",
            },
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result is None

    def test_ignores_workspace_dependency(self, tmp_path):
        pkg = self._write_pkg(tmp_path, {
            "dependencies": {
                "@team-deepiri/shared-utils": "workspace:*",
            },
        })
        result = self.proc._find_npm_dep_name(pkg, "deepiri-shared-utils")
        assert result is None


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
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._source_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        proc._source_repo = "deepiri-gpu-utils"
        proc._trigger = "tag"
        proc._active_target_refs = {"deepiri-gpu-utils": "v1.0.0"}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._regenerate_poetry_lock = lambda clone_path, package_name: True
        proc._create_pull_request = lambda repo_name, clone_path: "https://example.test/pr"

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

    def test_update_repo_updates_tag_pinned_poetry_dependency(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._trigger = "tag"
        proc._source_sha = "cccccccccccccccccccccccccccccccccccccccc"
        proc._source_repo = "deepiri-gpu-utils"
        proc._active_target_refs = {"deepiri-gpu-utils": "v0.1.1"}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._regenerate_poetry_lock = lambda clone_path, package_name: True
        proc._create_pull_request = lambda repo_name, clone_path: "https://example.test/pr"

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.poetry]
name = "consumer"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
deepiri-gpu-utils = {git = "https://github.com/Team-Deepiri/deepiri-gpu-utils.git", tag = "v0.1.0"}
""")

        result = proc._update_repo("consumer", "deepiri-gpu-utils", "v0.1.1")

        assert result == "updated"
        content = pyproject.read_text()
        assert 'tag = "v0.1.1"' in content
        assert "rev =" not in content

    def test_update_repo_skips_tag_pinned_poetry_on_push(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._trigger = "push"
        proc._source_sha = "dddddddddddddddddddddddddddddddddddddddd"
        proc._source_repo = "deepiri-gpu-utils"
        proc._active_target_refs = {"deepiri-gpu-utils": proc._source_sha}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._create_pull_request = lambda repo_name, clone_path: None

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.poetry]
name = "consumer"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
deepiri-gpu-utils = {git = "https://github.com/Team-Deepiri/deepiri-gpu-utils.git", tag = "v0.1.0"}
""")

        result = proc._update_repo("consumer", "deepiri-gpu-utils", proc._source_sha)

        assert result == "skipped"
        assert 'tag = "v0.1.0"' in pyproject.read_text()

    def test_update_repo_updates_tag_pinned_pep621_dependency(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._trigger = "tag"
        proc._source_sha = "f" * 40
        proc._source_repo = "deepiri-gpu-utils"
        proc._active_target_refs = {"deepiri-gpu-utils": "v0.2.0"}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._create_pull_request = lambda repo_name, clone_path: "https://example.test/pr"

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["setuptools>=68"]

[project]
name = "deepiri-ollama-utils"
version = "0.2.0"
dependencies = [
  "httpx>=0.27",
  "deepiri-gpu-utils @ git+https://github.com/Team-Deepiri/deepiri-gpu-utils.git@v0.1.0",
]
""")

        result = proc._update_repo("deepiri-ollama-utils", "deepiri-gpu-utils", "v0.2.0")

        assert result == "updated"
        content = pyproject.read_text()
        assert "@v0.2.0" in content
        assert 'version = "0.2.1"' in content

    def test_update_repo_uses_source_sha_for_pep621_rev_dependency(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._source_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        proc._source_repo = "deepiri-gpu-utils"
        proc._trigger = "tag"
        proc._active_target_refs = {"deepiri-gpu-utils": "v1.0.0"}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._create_pull_request = lambda repo_name, clone_path: "https://example.test/pr"

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "consumer"
version = "0.1.0"
dependencies = [
  "deepiri-gpu-utils @ git+https://github.com/Team-Deepiri/deepiri-gpu-utils.git@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
]
""")

        result = proc._update_repo("consumer", "deepiri-gpu-utils", "v1.0.0")

        assert result == "updated"
        assert "@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in pyproject.read_text()

    def test_update_repo_skips_tag_pinned_pep621_on_push(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._trigger = "push"
        proc._source_sha = "dddddddddddddddddddddddddddddddddddddddd"
        proc._source_repo = "deepiri-gpu-utils"
        proc._active_target_refs = {"deepiri-gpu-utils": proc._source_sha}
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        proc._create_pull_request = lambda repo_name, clone_path: None

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "consumer"
version = "0.1.0"
dependencies = [
  "deepiri-gpu-utils @ git+https://github.com/Team-Deepiri/deepiri-gpu-utils.git@v0.1.0",
]
""")

        result = proc._update_repo("consumer", "deepiri-gpu-utils", proc._source_sha)

        assert result == "skipped"
        assert "@v0.1.0" in pyproject.read_text()

    def test_platform_submodule_uses_consumer_push_sha(self, tmp_path, monkeypatch):
        from deepiri_cascade.parser.gitmodules import SubmoduleUpdateResult

        gpu_sha = "d1f8e92d5ec38f9a839ac9bade04cd71edd219b1"
        cyrex_sha = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        helox_sha = "ffffffffffffffffffffffffffffffffffffffff"

        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._trigger = "tag"
        proc._source_repo = "deepiri-gpu-utils"
        proc._source_sha = gpu_sha
        proc._active_target_refs = {
            "diri-cyrex": cyrex_sha,
            "diri-helox": helox_sha,
        }
        proc._last_pushed_sha = None

        platform = tmp_path / "platform"
        platform.mkdir()
        (platform / ".gitmodules").write_text("""
[submodule "diri-cyrex"]
    path = diri-cyrex
    url = git@github.com:Team-Deepiri/diri-cyrex.git
[submodule "diri-helox"]
    path = diri-helox
    url = git@github.com:Team-Deepiri/diri-helox.git
""")

        checkout_refs = []

        def fake_update(repo_path, submodule_path, new_ref, git_config=None):
            checkout_refs.append((submodule_path, new_ref))
            return SubmoduleUpdateResult(True)

        monkeypatch.setattr(
            "deepiri_cascade.parser.gitmodules.update_submodule_ref_result",
            fake_update,
        )
        proc._get_or_clone_repo = lambda repo_name: platform
        proc._create_pull_request = lambda repo_name, clone_path: "https://example.test/pr"

        result = proc._update_repo("deepiri-platform", "diri-cyrex", cyrex_sha)

        assert result == "updated"
        assert checkout_refs == [
            ("diri-cyrex", cyrex_sha),
            ("diri-helox", helox_sha),
        ]
        assert gpu_sha not in {ref for _, ref in checkout_refs}

    def test_cascade_records_pushed_sha_for_downstream_submodules(self):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.verbose = False
        proc._cascade_refs = {"deepiri-gpu-utils": "v0.2.0"}
        proc._last_pushed_sha = "cccccccccccccccccccccccccccccccccccccccc"

        proc._cascade_refs["diri-cyrex"] = proc._last_pushed_sha

        assert proc._cascade_refs["diri-cyrex"] == "c" * 40
        assert proc._cascade_refs["diri-cyrex"] != "d1f8e92d5ec38f9a839ac9bade04cd71edd219b1"

    def test_update_repo_fails_when_matching_submodule_update_fails(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._source_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        proc._get_or_clone_repo = lambda repo_name: tmp_path

        (tmp_path / ".gitmodules").write_text("""
[submodule "platform-services/shared/deepiri-shared-utils"]
    path = platform-services/shared/deepiri-shared-utils
    url = git@github.com:Team-Deepiri/deepiri-shared-utils.git
""")

        result_cls = __import__(
            "deepiri_cascade.parser.gitmodules",
            fromlist=["SubmoduleUpdateResult"],
        ).SubmoduleUpdateResult

        monkeypatch.setattr(
            "deepiri_cascade.parser.gitmodules.update_submodule_ref_result",
            lambda *args: result_cls(False, "submodule init", "auth failed"),
        )

        result = proc._update_repo(
            "deepiri-platform",
            "deepiri-shared-utils",
            "v1.2.3",
        )

        assert result == "failed"

    def test_update_repo_skips_when_matching_dependency_is_already_current(self, tmp_path):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.bump_type = "patch"
        proc.dry_run = False
        proc._active_target_refs = {"deepiri-shared-utils": "v1.2.3"}
        proc._get_default_branch_sha = lambda repo: None
        proc._get_tag_sha = lambda repo, tag: None
        proc._get_or_clone_repo = lambda repo_name: tmp_path
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {
                "@team-deepiri/shared-utils": "github:Team-Deepiri/deepiri-shared-utils#v1.2.3",
            },
        }))
        proc._regenerate_npm_lock = lambda clone_path: None
        proc._create_pull_request = lambda repo_name, clone_path: None

        result = proc._update_repo(
            "consumer",
            "deepiri-shared-utils",
            "v1.2.3",
        )

        assert result == "skipped"


class TestGitOperations:
    def test_get_or_clone_repo_does_not_recurse_all_submodules(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.token = "secret-token"
        proc.org = "team-deepiri"
        proc.work_dir = tmp_path
        proc._repo_cache = {}
        calls = []

        class Result:
            returncode = 0

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd[:2] == ["git", "clone"]:
                (tmp_path / "consumer").mkdir()
            return Result()

        monkeypatch.setattr("deepiri_cascade.cascade.subprocess.run", fake_run)

        result = proc._get_or_clone_repo("consumer")

        assert result == tmp_path / "consumer"
        clone_cmd = calls[0][0]
        assert clone_cmd[:2] == ["git", "clone"]
        assert "--recurse-submodules" not in clone_cmd
        assert any(call[0][:3] == ["git", "config", "--add"] for call in calls)

    def test_git_fetch_resets_without_updating_all_submodules(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.token = "secret-token"
        proc._get_default_branch = lambda repo_name: "main"
        calls = []

        class Result:
            returncode = 0

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return Result()

        monkeypatch.setattr("deepiri_cascade.cascade.subprocess.run", fake_run)

        assert proc._git_fetch(tmp_path, "consumer") is True
        assert ["git", "submodule", "update", "--init", "--recursive"] not in calls
        assert ["git", "fetch", "--all", "--prune"] in calls
        assert ["git", "reset", "--hard", "origin/main"] in calls

    def test_git_auth_config_args_rewrites_ssh_and_https_github_urls(self):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.token = "secret-token"

        args = proc._git_auth_config_args()

        assert args == [
            "-c",
            "url.https://x-access-token:secret-token@github.com/.insteadOf=git@github.com:",
            "-c",
            "url.https://x-access-token:secret-token@github.com/.insteadOf=https://github.com/",
        ]


class TestResolveUpdateRef:
    def test_resolve_semver_tag_to_default_branch_when_tag_missing(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc._source_repo = "deepiri-gpu-utils"
        proc._source_sha = "a" * 40
        proc._get_tag_sha = lambda repo, tag: None
        proc._get_default_branch_sha = lambda repo: "d" * 40

        resolved = proc._resolve_update_ref("diri-helox", "v0.1.1")
        assert resolved == "d" * 40

    def test_push_source_uses_source_sha(self):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc._source_repo = "deepiri-auth-service"
        proc._source_sha = "e" * 40

        resolved = proc._resolve_update_ref("deepiri-auth-service", "ignored")
        assert resolved == "e" * 40


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
        assert "//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}" in content
        assert "secret-token" not in content

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
        assert "//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}" in content
        assert "new-token" not in content


class TestAutoMerge:
    def test_ensure_repo_auto_merge_skips_when_already_enabled(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        proc._get_repository = lambda repo: {"allow_auto_merge": True}

        patch_calls = []
        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.patch",
            lambda *args, **kwargs: patch_calls.append((args, kwargs)),
        )

        assert proc._ensure_repo_auto_merge("consumer") is True
        assert patch_calls == []

    def test_ensure_repo_auto_merge_patches_repo_setting(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {"Authorization": "Bearer test"}
        proc._get_repository = lambda repo: {"allow_auto_merge": False}

        class Response:
            status_code = 200
            text = ""

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.patch",
            lambda url, **kwargs: Response(),
        )

        assert proc._ensure_repo_auto_merge("consumer") is True

    def test_pick_merge_method_prefers_squash(self):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc._get_repository = lambda repo: {
            "allow_squash_merge": True,
            "allow_merge_commit": True,
        }

        assert proc._pick_merge_method("consumer") == "SQUASH"

    def test_schedule_pull_request_auto_merge_enables_repo_and_pr(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        calls = []
        proc._ensure_repo_auto_merge = lambda repo: calls.append(("repo", repo)) or True
        proc._pick_merge_method = lambda repo: "SQUASH"
        proc._enable_auto_merge = lambda node_id, merge_method: (
            calls.append(("merge", node_id, merge_method)) or True
        )

        proc._schedule_pull_request_auto_merge(
            "consumer",
            {"node_id": "PR_123", "number": 42},
        )

        assert calls == [
            ("repo", "consumer"),
            ("merge", "PR_123", "SQUASH"),
        ]

    def test_enable_auto_merge_logs_graphql_error(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.headers = {}

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"errors": [{"message": "Auto merge is not allowed for this repository"}]}

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.post",
            lambda *args, **kwargs: Response(),
        )

        assert proc._enable_auto_merge("PR_123", "MERGE") is False


class TestPoetryLockRegeneration:
    def test_regenerate_poetry_lock_updates_changed_package_only(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.token = "secret-token"
        calls = []

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return Result()

        def fake_configure_git_auth(path):
            calls.append(("configure_git_auth", path))

        monkeypatch.setattr("deepiri_cascade.cascade.subprocess.run", fake_run)
        proc._configure_git_auth = fake_configure_git_auth
        proc._poetry_command = lambda: ["poetry"]

        assert proc._regenerate_poetry_lock(tmp_path, "deepiri-gpu-utils") is True

        assert calls[0] == ("configure_git_auth", tmp_path)
        assert calls[1][0] == [
            "poetry",
            "update",
            "--lock",
            "--no-interaction",
            "deepiri-gpu-utils",
        ]
        assert calls[1][1]["cwd"] == tmp_path

    def test_regenerate_poetry_lock_returns_false_on_failure(self, tmp_path, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.token = "secret-token"

        class Result:
            returncode = 1
            stdout = ""
            stderr = "git clone failed"

        monkeypatch.setattr(
            "deepiri_cascade.cascade.subprocess.run",
            lambda *args, **kwargs: Result(),
        )
        proc._configure_git_auth = lambda path: None
        proc._poetry_command = lambda: ["poetry"]

        assert proc._regenerate_poetry_lock(tmp_path, "deepiri-gpu-utils") is False


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
        assert calls[0][1]["env"]["NODE_AUTH_TOKEN"] == "secret-token"


class TestCloseSupersededPullRequests:
    """A newer cascade bump for the same dependency supersedes older open PRs."""

    def test_closes_older_pr_for_same_dependency_only(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        proc.closed = []

        class Resp:
            status_code = 200
            headers = {}

            @staticmethod
            def json():
                return [
                    {
                        "number": 11,
                        "head": {"ref": "deepiri-cascade/consumer/deps/old00001"},
                        "title": "deps: update deepiri-helox → v1.0.0",
                        "html_url": "url/11",
                    },
                    {
                        "number": 12,
                        "head": {"ref": "deepiri-cascade/consumer/deps/keep22222"},
                        "title": "deps: update deepiri-helox → v1.1.0",
                        "html_url": "url/12",
                    },
                    {
                        "number": 13,
                        "head": {"ref": "deepiri-cascade/consumer/deps/other3333"},
                        "title": "deps: update deepiri-sugar → v2.0.0",
                        "html_url": "url/13",
                    },
                ]

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.get", lambda *a, **k: Resp()
        )
        proc._close_pull_request = lambda *a, **k: proc.closed.append(
            (a[1], k.get("superseding_url", ""))
        )

        proc._close_superseded_pull_requests(
            "consumer",
            "deepiri-cascade/consumer/deps/keep22222",
            "deepiri-helox",
            superseding_url="https://github.com/newpr/252",
        )

        assert proc.closed == [(11, "https://github.com/newpr/252")]

    def test_skips_non_cascade_str(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        proc.closed = []

        class Resp:
            status_code = 200
            headers = {}

            @staticmethod
            def json():
                return [
                    {
                        "number": 7,
                        "head": {"ref": "feature/hand-led"},
                        "title": "deps: update deepiri-helox → v1.0.0",
                        "html_url": "url/7",
                    },
                    {
                        "number": 8,
                        "head": {"ref": "deepiri-cascade/consumer/deps/keep22222"},
                        "title": "deps: update deepiri-helox → v1.1.0",
                        "html_url": "url/8",
                    },
                ]

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.get", lambda *a, **k: Resp()
        )
        proc._close_pull_request = lambda *a, **k: proc.closed.append(a[1])

        proc._close_superseded_pull_requests(
            "consumer", "deepiri-cascade/consumer/deps/keep22222", "deepiri-helox"
        )

        assert proc.closed == []

    def test_close_pull_request_patches_state_and_comments(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        patch_calls = []
        post_calls = []

        class PatchResp:
            status_code = 200

        class PostResp:
            status_code = 201

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.patch",
            lambda url, **kw: patch_calls.append((url, kw)) or PatchResp(),
        )
        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.post",
            lambda url, **kw: post_calls.append((url, kw)) or PostResp(),
        )

        proc._close_pull_request("consumer", 11, "deps: update deepiri-helox → v1.0.0", superseding_url="https://github.com/x")

        assert patch_calls[0][0].endswith("/pulls/11")
        assert patch_calls[0][1]["json"] == {"state": "closed"}
        assert "issues/11/comments" in post_calls[0][0]
        assert "superseded by the newer dependency bump" in post_calls[0][1]["json"]["body"]

    def test_superseded_scan_paginates_through_link_header(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        proc.closed = []

        page1 = type("P1", (), {"status_code": 200, "headers": {
            "Link": '<https://api.github.com/repos/x/pulls?per_page=100&page=2>; rel="next"'
        }})()
        page1.json = lambda: [
            {
                "number": 21,
                "head": {"ref": "deepiri-cascade/consumer/deps/old11111"},
                "title": "deps: update deepiri-helox → v1.0.0",
                "html_url": "url/21",
            }
        ]
        page2 = type("P2", (), {"status_code": 200, "headers": {}})()
        page2.json = lambda: [
            {
                "number": 22,
                "head": {"ref": "deepiri-cascade/consumer/deps/old22222"},
                "title": "deps: update deepiri-helox → v1.1.0",
                "html_url": "url/22",
            }
        ]

        calls = {"n": 0}

        def fake_get(url, **kw):
            calls["n"] += 1
            return page1 if calls["n"] == 1 else page2

        monkeypatch.setattr("deepiri_cascade.cascade.httpx.get", fake_get)
        proc._close_pull_request = lambda *a, **k: proc.closed.append(a[1])

        proc._close_superseded_pull_requests(
            "consumer", "deepiri-cascade/consumer/deps/keep33333", "deepiri-helox"
        )

        assert calls["n"] == 2
        assert sorted(proc.closed) == [21, 22]

    def test_close_pull_request_accepts_202_as_success(self, monkeypatch):
        proc = CascadeProcessor.__new__(CascadeProcessor)
        proc.org = "team-deepiri"
        proc.headers = {}
        patch_calls = []

        class PatchResp:
            status_code = 202

        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.patch",
            lambda url, **kw: patch_calls.append(url) or PatchResp(),
        )
        monkeypatch.setattr(
            "deepiri_cascade.cascade.httpx.post",
            lambda url, **kw: None,
        )

        proc._close_pull_request(
            "consumer", 9, "deps: update deepiri-helox → v1.0.0",
            superseding_url="https://github.com/x",
        )

        assert patch_calls[0].endswith("/pulls/9")
