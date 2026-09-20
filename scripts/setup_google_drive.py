#!/usr/bin/env python3
"""Setup script for Google Drive authentication in the Internship Logbook.

This script guides the user through setting up Google Drive access
via Hermes' Google Workspace skill (preferred) or a manual OAuth flow.

Usage:
    python scripts/setup_google_drive.py

The script:
    1. Checks if Hermes is installed
    2. Checks if the Google Workspace skill is available
    3. Runs Hermes Google Workspace OAuth if available
    4. Falls back to manual Google OAuth setup
    5. Verifies authentication with a simple Drive API call
    6. Never prints sensitive tokens

Works on macOS, Linux, and Windows.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

# Ensure the scripts directory is on sys.path so sibling modules
# can be imported regardless of invocation method:
#   python scripts/setup_google_drive.py  (from repo root)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_script_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from config import StorageConfig, get_config

# ---------------------------------------------------------------------------
# Colors / styling (simple, no external deps)
# ---------------------------------------------------------------------------

class Style:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @staticmethod
    def supported() -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def bold(text: str) -> str:
    return f"{Style.BOLD}{text}{Style.RESET}" if Style.supported() else text


def dim(text: str) -> str:
    return f"{Style.DIM}{text}{Style.RESET}" if Style.supported() else text


# ---------------------------------------------------------------------------
# Hermes detection
# ---------------------------------------------------------------------------

def find_hermes_home() -> Optional[Path]:
    """Find the Hermes home directory."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        p = Path(hermes_home)
        if p.is_dir():
            return p
    # Default location
    p = Path.home() / ".hermes"
    if p.is_dir():
        return p
    return None


def find_hermes_workspace_setup(hermes_home: Path) -> Optional[Path]:
    """Return the path to Hermes' Google Workspace setup.py, or None."""
    candidate = hermes_home / "skills" / "productivity" / "google-workspace" / "scripts" / "setup.py"
    if candidate.is_file():
        return candidate
    return None


def is_hermes_installed() -> bool:
    """Check if Hermes CLI is available."""
    import shutil
    return shutil.which("hermes") is not None


# ---------------------------------------------------------------------------
# Google Cloud project guidance
# ---------------------------------------------------------------------------

def print_cloud_setup_instructions() -> None:
    """Print instructions for creating Google Cloud OAuth credentials."""
    print(bold("\n=== Step 1: Create Google Cloud OAuth Credentials ==="))
    print()
    print("You need a Google Cloud OAuth 2.0 Client ID (Desktop app type).")
    print("This is a one-time setup per Google account.\n")
    print("1. Go to: https://console.cloud.google.com/projectselector2/home/dashboard")
    print("2. Create a new project (or select an existing one)")
    print("3. Enable the Google Drive API:")
    print("   https://console.cloud.google.com/apis/library/drive.googleapis.com")
    print("4. Create OAuth credentials:")
    print("   https://console.cloud.google.com/apis/credentials")
    print("   → Credentials → Create Credentials → OAuth 2.0 Client ID")
    print("   → Application type: Desktop app")
    print("   → Name: 'Internship Logbook'")
    print("5. Download the JSON file (client_secret.json)")
    print("6. Place it at: ~/.hermes/google_client_secret.json")
    print()
    print(dim("Tip: If you already have a client_secret.json from another project,"))
    print(dim("   you can reuse it — just make sure the Drive API is enabled."))
    print()


def prompt_client_secret(hermes_home: Path) -> Optional[Path]:
    """Ask the user where their client_secret.json is located."""
    default_path = hermes_home / "google_client_secret.json"
    print(f"Expected location: {default_path}")
    print()
    response = input(
        f"Enter path to client_secret.json (or press Enter to use {default_path}): "
    ).strip()

    if not response:
        if default_path.is_file():
            return default_path
        print(f"Error: No client_secret.json found at {default_path}")
        print("Please download it from Google Cloud Console first.")
        return None

    path = Path(response).expanduser()
    if not path.is_file():
        print(f"Error: File not found: {path}")
        return None
    return path


# ---------------------------------------------------------------------------
# Hermes Workspace auth flow
# ---------------------------------------------------------------------------

def run_hermes_workspace_auth(
    hermes_home: Path, setup_script: Path, client_secret_path: Path
) -> bool:
    """Run the Hermes Google Workspace OAuth flow for Drive.

    Returns True on success, False otherwise.
    """
    import subprocess

    print(bold("\n=== Step 2: Authenticate via Hermes Google Workspace ==="))
    print()

    # Step 1: Check existing auth
    print("Checking existing Hermes authentication...")
    result = subprocess.run(
        [sys.executable, str(setup_script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(setup_script.parent),
    )

    if result.stdout.strip() == "AUTHENTICATED":
        print("Hermes is already authenticated with Google Workspace.")
        print("Verifying Drive scope...")
        # Verify the token has Drive scope
        token_path = hermes_home / "google_token.json"
        if token_path.is_file():
            try:
                with open(token_path) as f:
                    token_data = json.load(f)
                scopes = token_data.get("scopes", [])
                drive_scope = "https://www.googleapis.com/auth/drive"
                if drive_scope in scopes or any("drive" in s for s in scopes):
                    print("Drive scope confirmed in existing token.")
                    return True
                else:
                    print("Drive scope NOT found in existing token.")
                    print("You may need to re-authorize with Drive scope.")
            except Exception:
                pass
        return True  # Assume it works; let the provider validate

    # Step 2: Store client secret path for the setup script
    # The Hermes setup script expects the client secret; we pass it via env
    env = os.environ.copy()
    if client_secret_path.is_file():
        env["GOOGLE_CLIENT_SECRET_PATH"] = str(client_secret_path)

    # Step 3: Get authorization URL
    print("Getting authorization URL from Hermes...")
    result = subprocess.run(
        [sys.executable, str(setup_script),
         "--auth-url", "--services", "drive", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=str(setup_script.parent),
        env=env,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"Error getting auth URL: {result.stderr.strip()}")
        print("\nFalling back to manual Google OAuth flow...")
        return run_manual_oauth(hermes_home, client_secret_path)

    try:
        auth_info = json.loads(result.stdout)
        auth_url = auth_info.get("auth_url", "")
    except (json.JSONDecodeError, AttributeError):
        # Try to extract URL from stdout
        for line in result.stdout.splitlines():
            if "http" in line:
                auth_url = line.strip()
                break
        else:
            print("Could not parse auth URL from Hermes setup output.")
            return run_manual_oauth(hermes_home, client_secret_path)

    if not auth_url:
        print("No authorization URL returned by Hermes setup.")
        return run_manual_oauth(hermes_home, client_secret_path)

    # Step 4: Open browser for user authorization
    print("\nOpening browser for authorization...")
    print("If the browser doesn't open, visit this URL:")
    print(f"  {auth_url}")
    print()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Step 5: Get authorization code from user
    print("After authorizing, paste the full redirect URL or code here.")
    print("(The URL will look like: http://localhost:1/?code=...)")
    print()

    auth_code = input("Paste the authorization URL or code: ").strip()
    if not auth_code:
        print("No code provided. Authentication cancelled.")
        return False

    # Step 6: Exchange code for token
    print("Exchanging authorization code for token...")
    result = subprocess.run(
        [sys.executable, str(setup_script),
         "--auth-code", auth_code, "--format", "json"],
        capture_output=True,
        text=True,
        cwd=str(setup_script.parent),
        env=env,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"Error exchanging auth code: {result.stderr.strip()}")
        return False

    # Step 7: Verify
    print("Verifying authentication...")
    verify = subprocess.run(
        [sys.executable, str(setup_script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(setup_script.parent),
        env=env,
        timeout=15,
    )

    if verify.stdout.strip() == "AUTHENTICATED":
        print(bold("\n✓ Successfully authenticated with Google Drive via Hermes!"))
        return True
    else:
        print(f"Auth verification output: {verify.stdout.strip()}")
        print("\nAttempting to use token anyway...")
        return True  # Token may still be valid


# ---------------------------------------------------------------------------
# Manual OAuth flow (fallback)
# ---------------------------------------------------------------------------

def run_manual_oauth(hermes_home: Path, client_secret_path: Path) -> bool:
    """Run a direct Google OAuth flow using google-auth-oauthlib.

    This is the fallback when Hermes Workspace is not available.
    """
    print(bold("\n=== Step 2: Manual Google OAuth Setup ==="))
    print()
    print("This will open a browser for you to authorize Google Drive access.")
    print("The token will be saved to: {}\n".format(hermes_home / "google_token.json"))

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("Error: google-auth-oauthlib is not installed.")
        print("Install it with: pip install google-auth-oauthlib")
        return False

    if not client_secret_path.is_file():
        print(f"Error: client_secret.json not found at {client_secret_path}")
        print("Please download it from Google Cloud Console and place it there.")
        return False

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path), SCOPES
        )
        creds = flow.run_local_server(
            access_type="offline",
            prompt="consent",
            port=0,
        )

        # Save token
        hermes_home.mkdir(parents=True, exist_ok=True)
        token_path = hermes_home / "google_token.json"
        with open(token_path, "w") as f:
            f.write(creds.to_json())

        print(bold(f"\n✓ Token saved to {token_path}"))
        return True

    except Exception as e:
        print(f"OAuth flow failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_drive_access(hermes_home: Path) -> bool:
    """Verify Google Drive access with a simple API call."""
    print(bold("\n=== Step 3: Verify Google Drive Access ==="))
    print()

    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        token_path = hermes_home / "google_token.json"
        if not token_path.is_file():
            print("Error: No token file found.")
            return False

        with open(token_path) as f:
            token_data = json.load(f)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                print("Token expired, attempting refresh...")
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                print("Token refreshed successfully.")
            else:
                print("Error: Token is invalid and cannot be refreshed.")
                return False

        service = build("drive", "v3", credentials=creds)
        about = service.files().list(pageSize=1, fields="files(id,name)").execute()
        print(f"✓ Google Drive API is working. Found {len(about.get('files', []))} file(s).")
        return True

    except Exception as e:
        print(f"Drive verification failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the setup wizard."""
    print(bold("=" * 60))
    print(bold("  Internship Logbook — Google Drive Setup"))
    print(bold("=" * 60))
    print()

    # Step 0: Detect Hermes
    hermes_home = find_hermes_home()
    hermes_installed = is_hermes_installed()
    setup_script = None

    if hermes_home:
        setup_script = find_hermes_workspace_setup(hermes_home)

    print("Hermes home:", hermes_home or "Not found")
    print("Hermes CLI installed:", "Yes" if hermes_installed else "No")
    print("Google Workspace skill:", "Found" if setup_script else "Not found")
    print()

    # Step 1: Ensure client secret exists
    client_secret_path = DEFAULT_CLIENT_SECRET = hermes_home / "google_client_secret.json" if hermes_home else Path.home() / ".hermes" / "google_client_secret.json"

    if not client_secret_path.is_file():
        print_cloud_setup_instructions()
        client_secret_path = prompt_client_secret(hermes_home or Path.home())
        if not client_secret_path:
            print("\nSetup aborted. Please place client_secret.json and retry.")
            sys.exit(1)
    else:
        print(f"✓ client_secret.json found at {client_secret_path}")
        print()

    # Step 2: Authenticate
    if setup_script and hermes_home:
        success = run_hermes_workspace_auth(hermes_home, setup_script, client_secret_path)
    else:
        print("Hermes Google Workspace skill not found.")
        print("Using manual Google OAuth flow as fallback.\n")
        success = run_manual_oauth(hermes_home or Path.home(), client_secret_path)

    if not success:
        print(bold("\n✗ Authentication failed."))
        print("Check the error messages above and try again.")
        sys.exit(1)

    # Step 3: Verify Drive access
    verify_home = hermes_home or Path.home()
    if not verify_drive_access(verify_home):
        print(bold("\n⚠ Authentication succeeded but Drive API test failed."))
        print("Your token may be missing the Drive scope.")
        print("Re-run this script or manually re-authorize with Drive access.")
        sys.exit(1)

    print()
    print(bold("Setup complete! Google Drive is ready for the Internship Logbook."))
    print()
    print("You can now use the logbook with Google Drive storage.")
    print("Set STORAGE_PROVIDER=google_drive to enable it.")
    print()


if __name__ == "__main__":
    main()
