"""Cascade trigger types and ref resolution."""
from __future__ import annotations

import re
from typing import Literal, Optional

TriggerType = Literal["tag", "push"]

_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_SEMVER_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+")


def is_commit_sha(ref: str) -> bool:
    return bool(_SHA_RE.fullmatch(ref))


def display_ref(trigger: TriggerType, ref: str) -> str:
    """Human-readable ref for PR titles and logs."""
    if trigger == "push" and is_commit_sha(ref):
        return f"main@{ref[:8]}"
    return ref


def branch_name_suffix(ref: str) -> str:
    if is_commit_sha(ref):
        return ref[:8]
    return ref.replace("/", "-")
