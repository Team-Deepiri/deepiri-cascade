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
