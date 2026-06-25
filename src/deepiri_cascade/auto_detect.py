import json
import os
from typing import Optional, Tuple

import httpx

from .triggers import TriggerType, is_commit_sha


def detect_cascade_inputs(
    repo: Optional[str],
    tag: Optional[str],
    sha: Optional[str],
    trigger: Optional[str],
    token: str,
    org: str,
) -> Tuple[str, str, TriggerType, Optional[str]]:
    """Resolve repo, display ref, trigger type, and commit SHA from CLI or Actions payload."""
    event_repo, event_tag, event_sha, event_trigger = _read_github_event_payload()

    repo = repo or event_repo
    tag = tag or event_tag
    sha = sha or event_sha
    trigger = (trigger or event_trigger or "tag").lower()

    if trigger not in ("tag", "push"):
        trigger = "tag"

    if not repo:
        raise ValueError("Could not detect repository name. Use --repo flag.")

    if trigger == "push":
        if not sha:
            sha = _fetch_default_branch_sha(token, org, repo)
        if not sha:
            raise ValueError(
                "Could not detect commit SHA for push cascade. Use --sha or merge to default branch."
            )
        return repo, sha, "push", sha

    if not tag:
        tag = fetch_latest_tag(token, org, repo)
    if not tag:
        raise ValueError("Could not detect version tag. Use --tag flag.")

    resolved_sha = _fetch_tag_sha(token, org, repo, tag)
    return repo, tag, "tag", resolved_sha


def _read_github_event_payload() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return None, None, None, None

    with open(event_path) as f:
        event = json.load(f)

    repo = None
    tag = None
    sha = None
    trigger = None

    if "repository" in event:
        repo = event["repository"].get("name")

    client_payload = event.get("client_payload") or {}
    if client_payload:
        repo = client_payload.get("repo") or repo
        tag = client_payload.get("tag")
        sha = client_payload.get("sha")
        trigger = client_payload.get("trigger")

    if not tag and "release" in event:
        tag = event["release"].get("tag_name")
    elif not tag and "ref" in event:
        ref = event["ref"]
        if ref.startswith("refs/tags/"):
            tag = ref.replace("refs/tags/", "")

    if not sha and trigger == "push":
        sha = client_payload.get("sha") or event.get("after")

    return repo, tag, sha, trigger


def fetch_latest_tag(token: str, org: str, repo: str) -> Optional[str]:
    """Fetch the latest tag for a specific repo via GitHub API."""
    url = f"https://api.github.com/repos/{org}/{repo}/tags"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = httpx.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            tags = response.json()
            if tags:
                return tags[0]["name"]
    except Exception:
        pass

    return None


def _fetch_tag_sha(token: str, org: str, repo: str, tag: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{org}/{repo}/git/ref/tags/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        response = httpx.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        obj = response.json().get("object", {})
        sha = obj.get("sha")
        if obj.get("type") == "tag" and sha:
            tag_response = httpx.get(
                f"https://api.github.com/repos/{org}/{repo}/git/tags/{sha}",
                headers=headers,
                timeout=10,
            )
            if tag_response.status_code == 200:
                return tag_response.json().get("object", {}).get("sha")
        return sha
    except Exception:
        return None


def _fetch_default_branch_sha(token: str, org: str, repo: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{org}/{repo}/commits"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        response = httpx.get(
            url,
            headers=headers,
            params={"per_page": 1},
            timeout=10,
        )
        if response.status_code == 200:
            commits = response.json()
            if commits:
                return commits[0].get("sha")
    except Exception:
        pass
    return None


# Backwards-compatible helper used by older callers/tests.
def detect_repo_and_tag(repo, tag, token, org):
    resolved_repo, ref, trigger, _ = detect_cascade_inputs(repo, tag, None, "tag", token, org)
    if trigger == "push" and is_commit_sha(ref):
        raise ValueError("Push trigger requires --sha/--trigger push")
    return resolved_repo, ref
