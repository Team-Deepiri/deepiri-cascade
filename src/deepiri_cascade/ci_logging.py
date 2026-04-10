"""CI-friendly cascade diagnostics (GitHub Actions job summary + structured log line)."""

from __future__ import annotations

import json
import os
from typing import Dict, List


def compute_dependency_waves(graph: Dict[str, List[str]], source: str) -> List[List[str]]:
    """Topological waves of repos that depend (directly or transitively) on ``source``."""
    dependents = graph.get(source, [])
    if not dependents:
        return []

    waves: List[List[str]] = []
    processed: set[str] = set()
    current_wave = list(dependents)

    while current_wave:
        waves.append(current_wave)
        processed.update(current_wave)

        next_wave: List[str] = []
        for repo in current_wave:
            for dep in graph.get(repo, []):
                if dep not in processed and dep not in next_wave:
                    next_wave.append(dep)

        current_wave = next_wave

    return waves


def emit_cascade_plan_for_ci(
    org: str,
    source_repo: str,
    tag: str,
    graph: Dict[str, List[str]],
    waves: List[List[str]],
) -> None:
    """Append to ``GITHUB_STEP_SUMMARY`` when set; always print one JSON line for logs."""
    direct = sorted(graph.get(source_repo, []))
    payload = {
        "type": "deepiri_cascade_plan",
        "org": org,
        "source_repo": source_repo,
        "tag": tag,
        "direct_dependent_count": len(direct),
        "direct_dependents": direct,
        "wave_count": len(waves),
        "waves": waves,
    }
    print(json.dumps(payload), flush=True)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## Cascade dependency plan",
        "",
        f"**Organization:** `{org}`  ",
        f"**Release:** `{source_repo}` @ `{tag}`  ",
        f"**Direct dependents:** {len(direct)}  ",
        f"**Waves:** {len(waves)}  ",
        "",
    ]
    if direct:
        lines.append("### Direct dependents")
        lines.extend(f"- `{name}`" for name in direct)
        lines.append("")
    else:
        lines.append("*No direct dependents in the built graph — nothing will be updated.*")
        lines.append("")

    for i, wave in enumerate(waves):
        lines.append(f"### Wave {i}")
        lines.extend(f"- `{name}`" for name in wave)
        lines.append("")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
