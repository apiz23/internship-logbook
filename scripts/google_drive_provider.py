"""Google Drive storage provider for the Internship Logbook.

This module provides all Google Drive operations needed by the
Internship Logbook core logic. It works relative to a configured
root folder and provides the same interface as local storage.

All operations use the parent folder ID when possible to avoid
searching the entire Google Drive.

Usage:
    from scripts.google_drive_provider import GoogleDriveProvider
    provider = GoogleDriveProvider()
    provider.create_folder("daily")
    provider.upload_markdown("daily/2026/09/2026-09-08.md", content)
"""

from __future__ import annotations

import os
import json
import io
from pathlib import Path
from typing import Optional, List, Dict

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials

from config import StorageConfig, get_config
from google_drive_auth import get_service


class GoogleDriveProvider:
    """Google Drive storage provider for the Internship Logbook.

    All paths are relative to the configured root folder.
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or get_config()
        self.service = None
        self.root_folder_id = None
        self._initialized = False

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        if not self.config.is_google_drive():
            return False

        # If already initialized, skip re-auth
        if self._initialized and self.service is not None:
            return True

        self.service = get_service()
        if not self.service:
            return False

        # Get root folder ID
        self.root_folder_id = (
            os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
            or self.config.google_drive.root_folder_id
        )

        if self.root_folder_id == "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID":
            return False

        # Verify root folder exists
        if not self._verify_root_folder():
            return False

        self._initialized = True
        return True

    def _verify_root_folder(self) -> bool:
        """Verify the configured root folder exists and is accessible."""
        if not self.service or not self.root_folder_id:
            return False

        try:
            result = self.service.files().get(
                fileId=self.root_folder_id,
                fields="name,id,mimeType"
            ).execute()
            return result.get("mimeType") == "application/vnd.google-apps.folder"
        except Exception:
            return False

    def get_root_folder(self) -> Optional[Dict]:
        """Get information about the root folder."""
        if not self._initialized:
            if not self.authenticate():
                return None

        try:
            return self.service.files().get(
                fileId=self.root_folder_id,
                fields="name,id,mimeType,createdTime,modifiedTime"
            ).execute()
        except Exception:
            return None

    def find_folder(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Find a folder by name within a parent folder.

        Returns the folder ID if found, None otherwise.
        """
        if not self._initialized:
            if not self.authenticate():
                return None

        search_parent = parent_id or self.root_folder_id
        if not search_parent:
            return None

        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{search_parent}' in parents and trashed=false"
        )

        try:
            result = self.service.files().list(
                q=query,
                fields="files(id,name)",
                spaces="drive",
            ).execute()
            files = result.get("files", [])
            if files:
                return files[0]["id"]
            return None
        except Exception:
            return None

    def find_file(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Find a file by name within a parent folder.

        Returns the file ID if found, None otherwise.
        """
        if not self._initialized:
            if not self.authenticate():
                return None

        search_parent = parent_id or self.root_folder_id
        if not search_parent:
            return None

        query = (
            f"name='{name}' and '{search_parent}' in parents "
            f"and trashed=false"
        )

        try:
            result = self.service.files().list(
                q=query,
                fields="files(id,name)",
                spaces="drive",
            ).execute()
            files = result.get("files", [])
            if files:
                return files[0]["id"]
            return None
        except Exception:
            return None

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Create a folder within a parent folder.

        Returns the folder ID if created, None if it already exists
        or if creation failed.
        """
        if not self._initialized:
            if not self.authenticate():
                return None

        parent_id = parent_id or self.root_folder_id
        if not parent_id:
            return None

        # Check if folder already exists
        existing = self.find_folder(name, parent_id)
        if existing:
            return existing

        folder_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }

        try:
            result = self.service.files().create(
                body=folder_metadata,
                fields="id,name",
            ).execute()
            return result.get("id")
        except Exception:
            return None

    def list_files(self, parent_id: Optional[str] = None) -> List[Dict]:
        """List files and folders within a parent folder."""
        if not self._initialized:
            if not self.authenticate():
                return []

        search_parent = parent_id or self.root_folder_id
        if not search_parent:
            return []

        query = f"'{search_parent}' in parents and trashed=false"

        try:
            result = self.service.files().list(
                q=query,
                fields="files(id,name,mimeType)",
                spaces="drive",
            ).execute()
            return result.get("files", [])
        except Exception:
            return []

    def upload_file(self, path: str, content: str, parent_id: Optional[str] = None) -> bool:
        """Upload a Markdown file to Google Drive.

        path: relative path like "daily/2026/09/2026-09-08.md"
        content: the Markdown content to write
        parent_id: override parent folder (usually not needed)
        """
        if not self._initialized:
            if not self.authenticate():
                return False

        parent_id = parent_id or self.root_folder_id
        if not parent_id:
            return False

        # Navigate to the correct parent folder
        parts = Path(path).parts
        current_parent = parent_id

        for part in parts[:-1]:
            # Check if folder exists
            folder_id = self.find_folder(part, current_parent)
            if folder_id:
                current_parent = folder_id
            else:
                # Create it
                folder_id = self.create_folder(part, current_parent)
                if not folder_id:
                    return False
                current_parent = folder_id

        # Check if file already exists
        filename = parts[-1]
        existing_file_id = self.find_file(filename, current_parent)

        file_metadata = {"name": filename}

        if existing_file_id:
            # Update existing file
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/markdown",
                resumable=True,
            )
            try:
                self.service.files().update(
                    fileId=existing_file_id,
                    body=file_metadata,
                    media_body=media,
                ).execute()
                return True
            except Exception:
                return False
        else:
            # Create new file
            file_metadata["parents"] = [current_parent]
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/markdown",
            )
            try:
                result = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id,name",
                ).execute()
                return bool(result.get("id"))
            except Exception:
                return False

    def download_file(self, path: str) -> Optional[str]:
        """Download a Markdown file from Google Drive.

        Returns the content string if found, None otherwise.
        """
        if not self._initialized:
            if not self.authenticate():
                return None

        parent_id = self.root_folder_id
        if not parent_id:
            return None

        parts = Path(path).parts
        current_parent = parent_id

        for part in parts[:-1]:
            folder_id = self.find_folder(part, current_parent)
            if not folder_id:
                return None
            current_parent = folder_id

        filename = parts[-1]
        file_id = self.find_file(filename, current_parent)

        if not file_id:
            return None

        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            return fh.getvalue().decode("utf-8")
        except Exception:
            return None

    def create_or_update_markdown(
        self, path: str, content: str
    ) -> bool:
        """Create or update a Markdown file.

        This is the primary method for storing log entries.
        path: relative path like "daily/2026/09/2026-09-08.md"
        """
        if not self._initialized:
            if not self.authenticate():
                return False

        return self.upload_file(path, content)

    def ensure_structure(self) -> dict:
        """Ensure the target folder structure exists.

        Creates missing folders only. Returns a dict with
        found and created folder IDs.
        """
        if not self.authenticate():
            return {"error": "Authentication failed"}

        result = {"found": {}, "created": {}}
        base_folders = ["daily", "weekly", "monthly", "templates"]

        for folder_name in base_folders:
            folder_id = self.find_folder(folder_name, self.root_folder_id)
            if folder_id:
                result["found"][folder_name] = folder_id
            else:
                folder_id = self.create_folder(folder_name, self.root_folder_id)
                if folder_id:
                    result["created"][folder_name] = folder_id
                else:
                    result["found"][folder_name] = None

        return result


def get_provider() -> Optional[GoogleDriveProvider]:
    """Get a configured GoogleDriveProvider if enabled."""
    config = get_config()
    if not config.is_google_drive():
        return None
    provider = GoogleDriveProvider(config)
    if not provider.authenticate():
        return None
    return provider
