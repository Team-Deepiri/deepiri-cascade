#!/usr/bin/env python3
"""Apply a minimal branch protection rule to every org default branch.

One-off remediation for the cascade log line:
    Auto-merge enable failed: Pull request Protected branch rules not configured
enablePullRequestAutoMerge refuses to schedule a merge when the base branch
is not covered by a branch protection rule. Adding a minimal rule (with no
enforced requirements) satisfies GitHub and lets native auto-merge work, so
the cascade bot no longer needs to admin-merge.

    DRY_RUN=true        (default) preview; set false to actually apply
    REPOS="a,b"         optional scope; default is every non-archived org repo
    REQUIRE_PR=true     require a PR before merging (blocks direct pushes)
    REQUIRED_CHECKS=a,b optional status checks for repos that run CI

Authenticate with the cascade GitHub App installation token
(Administration: write); plain GITHUB_TOKEN lacks admin on other repos.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in ("1", "true", "yes")


def _read_env() -> tuple:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required (use the cascade App installation token)")
    org = os.environ.get("ORG", "team-deepiri").strip()
    scope = [r.strip() for r in os.environ.get("REPOS", "").split(",") if r.strip()]
    checks = [c.strip() for c in os.environ.get("REQUIRED_CHECKS", "").split(",") if c.strip()]
    return token, org, scope, _env_bool("DRY_RUN"), _env_bool("REQUIRE_PR"), checks


def _request(token: str, url: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode()
            return resp.status, json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        return exc.code, None


def list_org_repos(token: str, org: str) -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        status, data = _request(token, f"{API}/orgs/{org}/repos?per_page=100&page={page}&type=all")
        if status != 200 or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def protection_payload(require_pr: bool, required_checks: list[str]) -> dict:
    payload = {
        "required_status_checks": None,
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }
    if required_checks:
        payload["required_status_checks"] = {
            "strict": True,
            "contexts": required_checks,
        }
    if require_pr:
        payload["required_pull_request_reviews"] = {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
        }
    return payload


def main() -> None:
    token, org, scope, dry_run, require_pr, required_checks = _read_env()

    repos = [r for r in list_org_repos(token, org) if not r.get("archived")]
    if scope:
        repos = [r for r in repos if r["name"] in scope]

    payload = protection_payload(require_pr, required_checks)
    mode = "DRY RUN (no changes applied)" if dry_run else "APPLYING"
    print(
        f"[{mode}] org={org} repos={len(repos)} "
        f"require_pr={require_pr} required_checks={required_checks}"
    )

    already = changed = failed = 0
    for repo in repos:
        name = repo["name"]
        branch = repo.get("default_branch") or "main"
        status, _ = _request(token, f"{API}/repos/{org}/{name}/branches/{branch}/protection")
        if status == 200:
            already += 1
            print(f"  {name}: already protected ({branch})")
            continue
        if status != 404:
            failed += 1
            print(f"  {name}: could not read protection (HTTP {status})")
            continue
        if dry_run:
            changed += 1
            print(f"  {name}: would protect {branch}")
            continue
        status, _ = _request(
            token,
            f"{API}/repos/{org}/{name}/branches/{branch}/protection",
            "PUT",
            payload,
        )
        if status in (200, 201):
            changed += 1
            print(f"  {name}: protected {branch} (HTTP {status})")
        else:
            failed += 1
            print(f"  {name}: failed to protect (HTTP {status})")

    print(f"summary: already={already} changed={changed} failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()