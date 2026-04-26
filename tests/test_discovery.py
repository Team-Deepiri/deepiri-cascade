"""Tests for dependency resolution and graph building."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from deepiri_cascade.discovery import Discovery


REPOS = {
    "deepiri-shared-utils",
    "deepiri-api-gateway",
    "deepiri-auth-service",
    "deepiri-platform",
    "some-lib",
}


class TestResolveDepToRepo:
    """Tests for Discovery._resolve_dep_to_repo — the npm-name → repo-name mapper."""

    def setup_method(self):
        self.d = Discovery.__new__(Discovery)
        self.d.org = "team-deepiri"

    def test_org_scoped_with_deepiri_prefix(self):
        # @team-deepiri/shared-utils → deepiri-shared-utils
        assert self.d._resolve_dep_to_repo(
            "@team-deepiri/shared-utils", "^1.0.0", REPOS
        ) == "deepiri-shared-utils"

    def test_org_scoped_exact_match(self):
        # @team-deepiri/some-lib → some-lib (no deepiri- prefix)
        assert self.d._resolve_dep_to_repo(
            "@team-deepiri/some-lib", "^2.0.0", REPOS
        ) == "some-lib"

    def test_legacy_deepiri_scope(self):
        # @deepiri/shared-utils → deepiri-shared-utils
        assert self.d._resolve_dep_to_repo(
            "@deepiri/shared-utils", "^1.0.0", REPOS
        ) == "deepiri-shared-utils"

    def test_gitmodules_value_is_repo_name(self):
        assert self.d._resolve_dep_to_repo(
            "platform-services/shared/deepiri-shared-utils",
            "deepiri-shared-utils",
            REPOS,
        ) == "deepiri-shared-utils"

    def test_poetry_value_is_repo_name(self):
        assert self.d._resolve_dep_to_repo(
            "deepiri-shared-utils", "deepiri-shared-utils", REPOS
        ) == "deepiri-shared-utils"

    def test_unrelated_dep_returns_none(self):
        assert self.d._resolve_dep_to_repo("express", "^4.0.0", REPOS) is None

    def test_unknown_org_returns_none(self):
        assert self.d._resolve_dep_to_repo(
            "@other-org/foo", "^1.0.0", REPOS
        ) is None

    def test_version_string_not_in_repos(self):
        assert self.d._resolve_dep_to_repo(
            "@team-deepiri/shared-utils", "1.0.0", REPOS
        ) == "deepiri-shared-utils"

    def test_prefers_exact_match_over_prefixed(self):
        repos_with_both = {"shared-utils", "deepiri-shared-utils"}
        result = self.d._resolve_dep_to_repo(
            "@team-deepiri/shared-utils", "^1.0.0", repos_with_both
        )
        assert result == "shared-utils"


class TestBuildDependencyGraph:
    """Tests for Discovery.build_dependency_graph with mocked API calls."""

    def _make_discovery(self, repo_deps: dict):
        """Create a Discovery instance with mocked network calls.

        Args:
            repo_deps: mapping of repo_name → {dep_name: dep_value}
        """
        d = Discovery.__new__(Discovery)
        d.org = "team-deepiri"
        d.verbose = False
        d.headers = {}
        d._repo_cache = {}
        d._deps_cache = {}

        all_names = list(repo_deps.keys())
        d.list_org_repos = MagicMock(
            return_value=[{"name": n} for n in all_names]
        )
        d.fetch_file_content = MagicMock(return_value=None)

        for repo_name, deps in repo_deps.items():
            d._deps_cache[repo_name] = deps

        return d

    def test_npm_deps_detected(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-api-gateway": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
            "deepiri-auth-service": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
            "unrelated-repo": {
                "express": "^4.0.0",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")

        dependents = graph["deepiri-shared-utils"]
        assert "deepiri-api-gateway" in dependents
        assert "deepiri-auth-service" in dependents
        assert "unrelated-repo" not in dependents

    def test_gitmodules_deps_detected(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-platform": {
                "platform-services/shared/deepiri-shared-utils": "deepiri-shared-utils",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        assert "deepiri-platform" in graph["deepiri-shared-utils"]

    def test_mixed_npm_and_gitmodules(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-api-gateway": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
            "deepiri-platform": {
                "platform-services/shared/deepiri-shared-utils": "deepiri-shared-utils",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        dependents = graph["deepiri-shared-utils"]
        assert "deepiri-api-gateway" in dependents
        assert "deepiri-platform" in dependents

    def test_no_dependents(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "unrelated-repo": {"express": "^4.0.0"},
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        assert graph["deepiri-shared-utils"] == []

    def test_transitive_deps_in_graph(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-api-gateway": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
            "deepiri-web-frontend": {
                "@team-deepiri/api-gateway": "^1.0.0",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        assert "deepiri-api-gateway" in graph["deepiri-shared-utils"]
        assert "deepiri-web-frontend" in graph.get("deepiri-api-gateway", [])

    def test_transitive_deps_are_order_independent(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-admin-ui": {
                "@team-deepiri/web-frontend": "^1.0.0",
            },
            "deepiri-web-frontend": {
                "@team-deepiri/api-gateway": "^1.0.0",
            },
            "deepiri-api-gateway": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")

        assert graph["deepiri-shared-utils"] == ["deepiri-api-gateway"]
        assert graph["deepiri-api-gateway"] == ["deepiri-web-frontend"]
        assert graph["deepiri-web-frontend"] == ["deepiri-admin-ui"]

    def test_legacy_deepiri_scope(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {},
            "deepiri-auth-service": {
                "@deepiri/shared-utils": "^1.0.0",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        assert "deepiri-auth-service" in graph["deepiri-shared-utils"]

    def test_source_repo_not_listed_as_own_dependent(self):
        d = self._make_discovery({
            "deepiri-shared-utils": {
                "@team-deepiri/some-other": "^1.0.0",
            },
            "deepiri-api-gateway": {
                "@team-deepiri/shared-utils": "^1.0.0",
            },
        })

        graph = d.build_dependency_graph("deepiri-shared-utils", "v1.0.0")
        assert "deepiri-shared-utils" not in graph["deepiri-shared-utils"]
