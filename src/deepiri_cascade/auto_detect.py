import os
import json
import httpx


def detect_repo_and_tag(repo, tag, token, org):
    """
    Detect repo and tag from GitHub Actions context or API.
    
    If running in GitHub Actions, reads from github.event inputs.
    Otherwise, fetches latest tag from API.
    """
    if not repo or not tag:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            with open(event_path) as f:
                event = json.load(f)
            
            if not repo and "repository" in event:
                repo = event["repository"].get("name")
            
            if not tag and "release" in event:
                tag = event["release"].get("tag_name")
            elif not tag and "ref" in event:
                ref = event["ref"]
                if ref.startswith("refs/tags/"):
                    tag = ref.replace("refs/tags/", "")

    if not tag:
        tag = fetch_latest_tag(token, org, repo)

    if not repo:
        raise ValueError("Could not detect repository name. Use --repo flag.")

    if not tag:
        raise ValueError("Could not detect version tag. Use --tag flag.")

    return repo, tag


def fetch_latest_tag(token, org, repo):
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