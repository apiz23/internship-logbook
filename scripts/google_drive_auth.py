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

from requests import Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
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

def _is_token_file_corrupt(token_path: Path) -> bool:
    """Return True if the token file is empty or not valid JSON."""
    if not token_path.is_file():
        return True
    if token_path.stat().st_size == 0:
        return True
    try:
        with open(token_path) as f:
            json.load(f)
        return False
    except Exception:
        return True


def load_credentials(token_path: Path = None) -> Optional[Credentials]:
    """Load credentials from the token file, refreshing if needed.

    Handles the standard case (token exists but expired with a
    refresh token -> refresh + persist) and the corruption case
    (0-byte token file, e.g. from a failed write) by returning None
    so the caller can guide the user through re-authentication.

    Returns None if no valid credentials can be obtained.
    Never prints or logs the token contents.
    """
    if token_path is None:
        token_path = _default_token_path()

    # Corrupted/missing token file: cannot salvage. Caller should
    # attempt re-authentication (e.g. run Hermes setup again).
    if not token_path.is_file() or token_path.stat().st_size == 0:
        return None

    try:
        with open(token_path) as f:
            data = json.load(f)
        creds = Credentials.from_authorized_user_info(data, SCOPES)
    except Exception:
        # Unreadable/corrupt file -> caller handles re-auth
        return None

    if creds.valid:
        return creds

    # Expired but refreshable -> refresh and persist automatically
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            return creds
        except Exception:
            return None

    return None


def _reauthenticate(token_path: Path) -> Optional[Credentials]:
    """Launch the Hermes Google Workspace OAuth setup to obtain a fresh token.

    The token file is missing/corrupt, so there is no token to refresh.
    Prints the OAuth URL for the user; the user pastes the returned code
    and the code is exchanged for a fresh token.

    Returns valid credentials once the token file is valid, else None.
    """
    hermes_setup = find_hermes_workspace_setup()
    if hermes_setup:
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, str(hermes_setup), "--auth-url"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                print("\nGoogle Drive token is missing or corrupt. "
                      "Open this URL to re-authenticate:\n")
                print(proc.stdout.strip())
                print("\nAfter authorising, paste the code and re-run the sync.\n", flush=True)
        except Exception:
            pass
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
        return None, "Failed to build Drive service: {}".format(e)


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

    # Auto-reauthenticate if the token file is missing/corrupt.
    # (Sync failures used to show "authentication failed" without the
    # user being able to recover — now the script prompts them.)
    if _is_token_file_corrupt(token_path):
        if _reauthenticate(token_path) is not None:
            # Re-auth obtained a valid token; retry loading it.
            creds = load_credentials(token_path)
            if creds is not None:
                return True, "Authenticated via re-authentication."
        return False, "Token file missing/corrupt and re-authentication did not produce a valid token."

    creds = load_credentials(token_path)
    if creds is None:
        return False, "Token file exists but credentials could not be loaded or are invalid."

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            return False, "Token is expired but refreshable. Re-run setup to refresh."
        return False, "Token is invalid and cannot be refreshed."

    return True, "Authenticated."
