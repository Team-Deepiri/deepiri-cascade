__version__ = "0.1.0"

from .cli import main
from .auto_detect import detect_repo_and_tag
from .github_auth import get_token
from .discovery import Discovery
from .cascade import CascadeProcessor

__all__ = [
    "main",
    "detect_repo_and_tag",
    "get_token",
    "Discovery",
    "CascadeProcessor",
]