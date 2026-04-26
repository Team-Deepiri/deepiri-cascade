"""Tests for CascadeProcessor helpers."""

from deepiri_cascade.cascade import CascadeProcessor


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
