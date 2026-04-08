import os


def get_token():
    """Get GitHub token from environment or other sources."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    token = os.environ.get("GH_TOKEN")
    if token:
        return token

    return None


def get_token_source(token):
    """Return string describing where token came from."""
    if os.environ.get("GITHUB_TOKEN"):
        return "GITHUB_TOKEN environment variable"
    if os.environ.get("GH_TOKEN"):
        return "GH_TOKEN environment variable"
    return "provided via --token flag"