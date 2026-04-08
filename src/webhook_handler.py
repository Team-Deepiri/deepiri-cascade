#!/usr/bin/env python3
"""
GitHub App webhook handler for deepiri-cascade.

This script receives webhook events from the GitHub App and triggers
the cascade workflow via repository_dispatch.

Usage:
    python webhook_handler.py <payload.json>
"""
import os
import sys
import json
import httpx
import jwt
import time
from pathlib import Path

APP_ID = os.environ.get("DEEPIRI_CASCADE_APP_ID")
PRIVATE_KEY = os.environ.get("DEEPIRI_CASCADE_APP_PRIVATE_KEY")
ORG = "team-deepiri"
TARGET_REPO = "deepiri-cascade"


def load_private_key():
    """Load private key from env or file."""
    if PRIVATE_KEY:
        return PRIVATE_KEY
    
    key_path = Path("/secrets/deepiri-cascade/private-key.pem")
    if key_path.exists():
        return key_path.read_text()
    
    raise ValueError("Private key not found")


def create_jwt(app_id: str, private_key: str) -> str:
    """Create JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iss": app_id,
        "iat": now,
        "exp": now + 600,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token(app_id: str, private_key: str) -> str:
    """Get installation access token."""
    jwt_token = create_jwt(app_id, private_key)
    
    url = f"https://api.github.com/app/installations"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    
    resp = httpx.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"Failed to get installations: {resp.text}")
    
    installations = resp.json()
    if not installations:
        raise Exception("No installations found")
    
    install_id = installations[0]["id"]
    
    url = f"https://api.github.com/app/installations/{install_id}/access_tokens"
    resp = httpx.post(url, headers=headers, json={}, timeout=10)
    if resp.status_code != 201:
        raise Exception(f"Failed to get token: {resp.text}")
    
    return resp.json()["token"]


def trigger_workflow(token: str, repo: str, event_type: str, payload: dict):
    """Trigger a repository dispatch event."""
    url = f"https://api.github.com/repos/{ORG}/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    
    data = {
        "event_type": event_type,
        "client_payload": payload,
    }
    
    resp = httpx.post(url, headers=headers, json=data, timeout=30)
    if resp.status_code != 204:
        print(f"Error triggering workflow: {resp.status_code} - {resp.text}")
        return False
    
    return True


def handle_tag_push(payload: dict) -> dict:
    """Handle tag push event."""
    repo = payload.get("repository", {}).get("name")
    ref = payload.get("ref", "")
    
    if not ref.startswith("refs/tags/"):
        return {"skipped": "not a tag"}
    
    tag = ref.replace("refs/tags/", "")
    
    if not tag.startswith("v"):
        return {"skipped": "not a version tag"}
    
    return {
        "repo": repo,
        "tag": tag,
        "action": "cascade",
    }


def main():
    if len(sys.argv) < 2:
        # Read from stdin for GitHub Actions
        payload = json.load(sys.stdin)
    else:
        with open(sys.argv[1]) as f:
            payload = json.load(f)
    
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    print(f"Received event: {event}")
    
    if event == "push":
        result = handle_tag_push(payload)
    else:
        result = {"skipped": f"unknown event: {event}"}
    
    if "skipped" in result:
        print(f"Skipped: {result['skipped']}")
        return
    
    print(f"Triggering cascade for {result['repo']} {result['tag']}")
    
    try:
        app_id = APP_ID or os.environ.get("APP_ID")
        private_key = load_private_key()
        
        token = get_installation_token(app_id, private_key)
        success = trigger_workflow(
            token,
            TARGET_REPO,
            "cascade-trigger",
            result,
        )
        
        if success:
            print(f"Successfully triggered cascade for {result['repo']}:{result['tag']}")
        else:
            print("Failed to trigger cascade")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()