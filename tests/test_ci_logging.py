"""Tests for CI / wave helpers."""

from deepiri_cascade.ci_logging import compute_dependency_waves


def test_compute_dependency_waves_linear_chain():
    graph = {
        "lib-a": ["app-b"],
        "app-b": ["app-c"],
        "app-c": [],
    }
    assert compute_dependency_waves(graph, "lib-a") == [["app-b"], ["app-c"]]


def test_compute_dependency_waves_diamond():
    graph = {
        "base": ["mid-x", "mid-y"],
        "mid-x": ["top"],
        "mid-y": ["top"],
        "top": [],
    }
    waves = compute_dependency_waves(graph, "base")
    assert waves[0] == ["mid-x", "mid-y"]
    assert waves[1] == ["top"]


def test_compute_dependency_waves_no_dependents():
    assert compute_dependency_waves({"x": []}, "x") == []
