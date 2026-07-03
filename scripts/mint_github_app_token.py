#!/usr/bin/env python3
"""Mint a GitHub App installation token for cascade workflows."""

from __future__ import annotations

import os
import sys
import time

import httpx
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key

API = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(message)


def normalize_pem(raw: str) -> str:
    pem = raw.replace("\\n", "\n").strip()
    if not pem:
        _fail("APP_PRIVATE_KEY is empty")
    if "BEGIN" not in pem or "PRIVATE KEY" not in pem:
        _fail(
            "APP_PRIVATE_KEY does not look like a PEM private key. "
            "Paste the full downloaded .pem file into the repo secret."
        )
    return pem


def validate_private_key(pem: str) -> None:
    try:
        load_pem_private_key(pem.encode(), password=None)
    except Exception as exc:  # noqa: BLE001 - surface exact OpenSSL/cryptography error
        _fail(
            "APP_PRIVATE_KEY is not a valid PEM private key. "
            f"Re-upload the GitHub App .pem from App settings. ({exc})"
        )


def create_app_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": app_id, "iat": now - 60, "exp": now + 600},
        private_key_pem,
        algorithm="RS256",
    )


def resolve_installation_id(app_jwt: str, owner: str) -> int:
    headers = {**API_HEADERS, "Authorization": f"Bearer {app_jwt}"}

    org_resp = httpx.get(f"{API}/orgs/{owner}/installation", headers=headers, timeout=30)
    if org_resp.status_code == 200:
        return int(org_resp.json()["id"])

    installs_resp = httpx.get(f"{API}/app/installations", headers=headers, timeout=30)
    if installs_resp.status_code != 200:
        _fail(
            "GitHub App authentication failed. Verify APP_ID matches APP_PRIVATE_KEY "
            f"and the App is installed on {owner}. ({installs_resp.status_code}: "
            f"{installs_resp.text})"
        )

    installs = installs_resp.json()
    if not installs:
        _fail(f"No GitHub App installation found for owner {owner!r}")

    for install in installs:
        account = install.get("account") or {}
        if account.get("login", "").lower() == owner.lower():
            return int(install["id"])

    return int(installs[0]["id"])


def mint_installation_token(app_jwt: str, installation_id: int) -> str:
    headers = {**API_HEADERS, "Authorization": f"Bearer {app_jwt}"}
    resp = httpx.post(
        f"{API}/app/installations/{installation_id}/access_tokens",
        headers=headers,
        json={},
        timeout=30,
    )
    if resp.status_code != 201:
        _fail(f"Failed to mint installation token ({resp.status_code}: {resp.text})")
    return str(resp.json()["token"])


def main() -> None:
    app_id = os.environ.get("APP_ID", "").strip()
    owner = os.environ.get("GITHUB_APP_OWNER", "team-deepiri").strip()
    raw_key = os.environ.get("APP_PRIVATE_KEY", "")

    if not app_id:
        _fail("APP_ID is empty")
    if not app_id.isdigit():
        _fail("APP_ID must be the numeric GitHub App ID, not the OAuth client ID")

    private_key = normalize_pem(raw_key)
    validate_private_key(private_key)

    app_jwt = create_app_jwt(app_id, private_key)
    installation_id = resolve_installation_id(app_jwt, owner)
    token = mint_installation_token(app_jwt, installation_id)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"token={token}\n")
            handle.write(f"installation-id={installation_id}\n")
    else:
        print(token)


if __name__ == "__main__":
    main()
