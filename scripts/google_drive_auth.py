"""Google Drive authentication module for the Internship Logbook.

Handles OAuth2 Desktop Application flow using google-auth-oauthlib.
Tokens are stored at ~/.hermes/google_token.json and never exposed
in logs, reports, or the public repository.

Usage:
    python scripts/google_drive_auth.py --check
    python scripts/google_drive_auth.py --auth-url
    python scripts/google_drive_auth.py --test
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Narrowest practical Google Drive scope
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Path to the user's OAuth client secret
CREDENTIALS_PATH = str(Path.home() / ".hermes" / "google_client_secret.json")
TOKEN_PATH = str(Path.home() / ".hermes" / "google_token.json")


def check_credentials() -> bool:
    """Check that the client secret file exists."""
    if not os.path.exists(CREDENTIALS_PATH):
        print(
            f"Error: OAuth client secret not found at {CREDENTIALS_PATH}\n"
            "Please download google_client_secret.json from the "
            "Google Cloud Console and place it at that path.\n"
            "See: https://console.cloud.google.com/apis/credentials"
        )
        return False
    return True


def get_credentials() -> Optional[Credentials]:
    """Get valid OAuth credentials, refreshing or re-authenticating if needed."""
    creds = None

    # Try loading existing token
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            pass

    # Refresh if valid
    if creds and creds.valid:
        return creds

    # Refresh if expired but has refresh token
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds)
            return creds
        except Exception as e:
            print(f"Token refresh failed: {e}")

    # Need to authenticate
    if not check_credentials():
        return None

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    # Try to open browser with local server
    try:
        auth_url = flow.authorization_url(access_type="offline")
        webbrowser.open(auth_url)
        print(f"\nBrowser opened for authorization.\n"
              f"If it didn't open, visit this URL:\n{auth_url}\n")
        creds = flow.run_local_server(port=0)
        save_token(creds)
        return creds
    except Exception:
        pass

    # Fallback: prompt for manual code
    code = input("Enter the authorization code: ").strip()
    try:
        flow_obj = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        flow_obj.fetch_token(code=code)
        creds = flow_obj.credentials
        save_token(creds)
        return creds
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None


def save_token(creds: Credentials) -> None:
    """Save OAuth token to ~/.hermes/google_token.json."""
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f)


def get_service() -> Optional[object]:
    """Authenticate and return a Google Drive API service object."""
    creds = get_credentials()
    if not creds:
        return None
    try:
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        print(f"Failed to create Drive API service: {e}")
        return None


def test_authentication() -> dict:
    """Test authentication and root folder access.

    Returns a dict with safe information only (no credentials/tokens).
    """
    service = get_service()
    if not service:
        return {"status": "failed", "error": "Authentication failed"}

    root_folder_id = _get_root_folder_id()
    if not root_folder_id:
        return {"status": "failed", "error": "No root folder configured"}

    try:
        folder = service.files().get(fileId=root_folder_id, fields="name,id").execute()
        return {
            "status": "success",
            "root_folder_name": folder.get("name"),
            "root_folder_id": folder.get("id"),
            "message": "Authentication successful",
        }
    except Exception as e:
        return {"status": "failed", "error": f"Cannot access root folder: {e}"}


def _get_root_folder_id() -> Optional[str]:
    """Get the configured root folder ID from environment or config."""
    return os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")


def main():
    """CLI entry point for the authentication script."""
    if "--check" in sys.argv:
        if check_credentials():
            print("Credentials file found")
            service = get_service()
            if service:
                print("Authentication successful")
                result = test_authentication()
                if result["status"] == "success":
                    print(f"Root folder accessible: {result['root_folder_name']} ({result['root_folder_id']})")
                else:
                    print(f"Root folder error: {result.get('error')}")
            else:
                print("Authentication failed — check credentials")
        else:
            sys.exit(1)

    elif "--auth-url" in sys.argv:
        if not check_credentials():
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        auth_url = flow.authorization_url(access_type="offline")
        print(auth_url)

    elif "--test" in sys.argv:
        result = test_authentication()
        if result["status"] == "success":
            print("Authentication successful")
            print(f"Root folder accessible")
            print(f"Root folder name: {result['root_folder_name']}")
            print(f"Root folder ID: {result['root_folder_id']}")
        else:
            print(f"Authentication failed: {result.get('error')}")
            sys.exit(1)

    else:
        print("Usage:")
        print("  python google_drive_auth.py --check")
        print("  python google_drive_auth.py --auth-url")
        print("  python google_drive_auth.py --test")


if __name__ == "__main__":
    main()
