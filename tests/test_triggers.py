"""Tests for cascade trigger helpers."""
from deepiri_cascade.triggers import branch_name_suffix, display_ref, is_commit_sha


def test_is_commit_sha():
    assert is_commit_sha("a" * 40)
    assert not is_commit_sha("v1.0.0")
    assert not is_commit_sha("abc")


def test_display_ref_push():
    sha = "b" * 40
    assert display_ref("push", sha) == f"main@{sha[:8]}"


def test_display_ref_tag():
    assert display_ref("tag", "v1.2.3") == "v1.2.3"


def test_branch_name_suffix():
    sha = "c" * 40
    assert branch_name_suffix(sha) == sha[:8]
    assert branch_name_suffix("v1.0.0") == "v1.0.0"
