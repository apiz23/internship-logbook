"""Google Drive authentication for the Internship Logbook.

This module provides an abstraction over Google Drive authentication
that prefers Hermes' Google Workspace OAuth setup when available,
and falls back to direct Google OAuth when it is not.

Token storage:
    Hermes Google Workspace: ~/.hermes/google_token.json
    Manual fallback:         ~/.hermes/google_token.json  (same path)

Client secret:
    Hermes Google Workspace: provided by the user via --client-secret
    Manual fallback:         ~/.hermes/google_client_secret.json

Never log, print, or expose tokens, refresh tokens, or client secrets.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------------------------------------------------------
# Paths (never hardcode a specific user's home — always use Path.home())
# ---------------------------------------------------------------------------

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))

def _get_hermes_home() -> Path:
    """Return the Hermes home directory, resolved at call time."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        p = Path(hermes_home)
        if p.is_dir():
            return p
    return Path.home() / ".hermes"


def _default_token_path() -> Path:
    return _get_hermes_home() / "google_token.json"


def _default_client_secret_path() -> Path:
    return _get_hermes_home() / "google_client_secret.json"

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ---------------------------------------------------------------------------
# Hermes Google Workspace discovery
# ---------------------------------------------------------------------------

def find_hermes_workspace_setup() -> Optional[Path]:
    """Return the path to Hermes' Google Workspace setup.py, or None.

    Searches:
        1. $HERMES_HOME/skills/productivity/google-workspace/scripts/setup.py
        2. Adjacent to this script's parent (repo checkout layout)
    """
    # 1. Hermes-installed location (resolved at call time)
    hermes_home = _get_hermes_home()
    hermes_skill = hermes_home / "skills" / "productivity" / "google-workspace" / "scripts" / "setup.py"
    if hermes_skill.is_file():
        return hermes_skill

    # 2. Repo checkout layout (internship-logbook/scripts/../skills/... or
    #    internship-logbook/ as a standalone repo)
    repo_root = Path(__file__).resolve().parent.parent
    # Check if there's a skills/ directory at repo root
    repo_skill = repo_root / "skills" / "productivity" / "google-workspace" / "scripts" / "setup.py"
    if repo_skill.is_file():
        return repo_skill

    # Also check the installed site-packages location
    for site_dir in sys.path:
        candidate = Path(site_dir) / "hermes" / "skills" / "productivity" / "google-workspace" / "scripts" / "setup.py"
        if candidate.is_file():
            return candidate

    return None


def hermes_workspace_available() -> bool:
    """Return True if Hermes Google Workspace skill is installed."""
    return find_hermes_workspace_setup() is not None


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def token_is_valid(token_path: Path = None) -> bool:
    """Return True if a valid (non-expired) token exists at the given path."""
    if token_path is None:
        token_path = _default_token_path()
    try:
        with open(token_path) as f:
            data = json.load(f)
        creds = UserCredentials.from_authorized_user_info(data, SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token is not None)
    except Exception:
        return False


def load_credentials(token_path: Path = None) -> Optional[Credentials]:
    """Load credentials from the token file, refreshing if needed.

    Returns None if no valid credentials can be obtained.
    Never prints or logs the token contents.
    """
    if token_path is None:
        token_path = _default_token_path()

    try:
        with open(token_path) as f:
            data = json.load(f)
        creds = UserCredentials.from_authorized_user_info(data, SCOPES)

        if creds.valid:
            return creds

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Persist refreshed token
                _save_token(creds, token_path)
                return creds
            except Exception:
                return None

        return None
    except Exception:
        return None


def _save_token(creds: Credentials, token_path: Path) -> None:
    """Save credentials token to disk. Never logs the token value."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())


# ---------------------------------------------------------------------------
# Main credential resolution
# ---------------------------------------------------------------------------

def get_credentials(
    token_path: Optional[Path] = None,
    client_secret_path: Optional[Path] = None,
) -> Tuple[Optional[Credentials], str]:
    """Resolve Google Drive credentials.

    Returns (credentials_or_None, status_message).

    Priority:
        1. Load existing valid token from token_path
        2. If expired but refreshable, refresh it
        3. If no valid token, return None with instructions

    The status_message is safe to show to the user — it never contains
    tokens, refresh tokens, or client secrets.
    """
    if token_path is None:
        token_path = _default_token_path()
    if client_secret_path is None:
        client_secret_path = _default_client_secret_path()

    # 1. Try loading an existing valid token
    creds = load_credentials(token_path)
    if creds:
        return creds, "Authenticated via existing token."

    # 2. Token file exists but is invalid/expired with no refresh token
    if token_path.is_file():
        return None, (
            "Token file exists but is invalid or expired without a refresh token. "
            "Please re-run setup: python scripts/setup_google_drive.py"
        )

    # 3. No token at all — guide user through setup
    hermes_setup = find_hermes_workspace_setup()
    if hermes_setup:
        return None, (
            "No Google Drive token found. Hermes Google Workspace skill is installed.\n"
            "Run: python scripts/setup_google_drive.py\n"
            "Or manually: python {} --auth-url --services drive --format json".format(hermes_setup)
        )

    return None, (
        "No Google Drive token found and Hermes Google Workspace skill is not installed.\n"
        "Install Hermes and the google-workspace skill, or run setup_google_drive.py "
        "for manual OAuth setup."
    )


def build_drive_service(
    token_path: Optional[Path] = None,
    client_secret_path: Optional[Path] = None,
):
    """Build a Google Drive API service object.

    Returns (service_or_None, error_message_or_None).
    """
    if token_path is None:
        token_path = _default_token_path()
    if client_secret_path is None:
        client_secret_path = _default_client_secret_path()

    creds, msg = get_credentials(token_path, client_secret_path)
    if creds is None:
        return None, msg

    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to build Drive service: {e}"


def check_auth(
    token_path: Optional[Path] = None,
    client_secret_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Check whether Google Drive authentication is configured and valid.

    Returns (is_authenticated, message).
    """
    if token_path is None:
        token_path = _default_token_path()
    if client_secret_path is None:
        client_secret_path = _default_client_secret_path()

    if not token_path.is_file():
        return False, "No token file found at {}.".format(token_path)

    creds = load_credentials(token_path)
    if creds is None:
        return False, "Token file exists but credentials could not be loaded or are invalid."

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            return False, "Token is expired but refreshable. Re-run setup to refresh."
        return False, "Token is invalid and cannot be refreshed."

    return True, "Authenticated."


# ---------------------------------------------------------------------------
# Request context (used by tests)
# ---------------------------------------------------------------------------

class Request:
    """Minimal stub for google.auth.transport.requests.Request."""

    def __call__(self):
        import requests
        return requests.Request()
