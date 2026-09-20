"""One-way Google Drive synchronization for the Internship Logbook.

This module provides a synchronization layer that copies local
Markdown files to Google Drive. The local repository remains the
canonical source of truth at all times.

Architecture:
    Local Markdown -> Google Drive

Sync rules:
- Local is always written/updated first.
- After a successful local write, Drive sync is attempted.
- If Drive sync fails, the local file is preserved and the failure
  is reported; the user can retry later.
- Files are matched by local relative path; duplicate Drive files
  for the same path are never created.
- Drive files are never downloaded and used to overwrite local files.
- Drive files are not deleted merely because a local file was deleted.

Usage:
    from google_drive_sync import sync_local_paths, GoogleDriveSync
    summary = sync_local_paths(["daily/2026-09-09.md"])
    print(summary)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from google_drive_provider import GoogleDriveProvider


@dataclass
class SyncSummary:
    """Result of a synchronization run."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "Created": self.created,
            "Updated": self.updated,
            "Unchanged": self.unchanged,
            "Failed": self.failed,
            "Skipped": self.skipped,
            "Errors": self.errors,
        }

    def print_report(self) -> None:
        print("Google Drive Sync")
        print("-----------------")
        print(f"Created: {self.created}")
        print(f"Updated: {self.updated}")
        print(f"Unchanged: {self.unchanged}")
        print(f"Failed: {self.failed}")
        print(f"Skipped: {self.skipped}")
        if self.errors:
            print("Errors:")
            for error in self.errors:
                print(f"  - {error}")


class GoogleDriveSync:
    """One-way synchronizer from local Markdown files to Google Drive."""

    def __init__(self, provider: Optional[GoogleDriveProvider] = None) -> None:
        self.provider = provider or GoogleDriveProvider()

    def _drive_path(self, local_path: str) -> str:
        """Return a stable Drive path for a local relative path."""
        path = local_path.strip().lstrip("/").lstrip("\\")
        if not path:
            raise ValueError("Empty local path")
        return path.replace("\\", "/")

    def _ensure_parent_folder(self, drive_path: str) -> Optional[str]:
        """Ensure all folders in drive_path exist under the root and return the leaf parent ID."""
        if not self.provider._initialized:
            if not self.provider.authenticate():
                return None

        parts = drive_path.split("/")
        if len(parts) <= 1:
            return self.provider.root_folder_id

        current_parent = self.provider.root_folder_id
        for part in parts[:-1]:
            if not part:
                continue
            folder_id = self.provider.find_folder(part, current_parent)
            if folder_id:
                current_parent = folder_id
            else:
                folder_id = self.provider.create_folder(part, current_parent)
                if not folder_id:
                    return None
                current_parent = folder_id
        return current_parent

    def _existing_drive_content(self, path: str) -> Optional[str]:
        """Return existing Drive content for a path, or None if missing."""
        parts = path.split("/")
        if not parts:
            return None

        if not self.provider._initialized:
            if not self.provider.authenticate():
                return None

        current_parent = self.provider.root_folder_id
        for part in parts[:-1]:
            if not part:
                continue
            folder_id = self.provider.find_folder(part, current_parent)
            if not folder_id:
                return None
            current_parent = folder_id

        filename = parts[-1]
        file_id = self.provider.find_file(filename, current_parent)
        if not file_id:
            return None
        return self.provider.download_file(path)

    def _file_needs_update(self, drive_path: str, content: str) -> bool:
        """Return True if the Drive file should be updated/created."""
        existing = self._existing_drive_content(drive_path)
        if existing is None:
            return True
        return existing != content

    def sync_file(self, local_path: str, content: str) -> Optional[str]:
        """Synchronize one local Markdown file to Google Drive.

        Returns:
            "created", "updated", "unchanged", or None on failure/skip.
        """
        try:
            drive_path = self._drive_path(local_path)
        except ValueError:
            return None

        # Reuse one authenticated provider instance for the whole run
        if not self.provider._initialized:
            if not self.provider.authenticate():
                return None

        # Check if file already exists on Drive
        existing = self._existing_drive_content(drive_path)
        if existing is not None and existing == content:
            return "unchanged"

        # Upload using root_folder_id so upload_file navigates
        # the full relative path correctly
        upload_result = self.provider.upload_file(drive_path, content, self.provider.root_folder_id)
        if not upload_result:
            return None

        # Determine created vs updated based on pre-upload check
        return "created" if existing is None else "updated"

    def sync_local_paths(self, paths: List[str], contents: List[str]) -> SyncSummary:
        """Synchronize multiple local Markdown files to Google Drive.

        paths and contents must be aligned by index.

        Returns a SyncSummary with counts.
        """
        summary = SyncSummary()

        if not paths:
            return summary

        if not self.provider.authenticate():
            summary.failed = len(paths)
            summary.errors.append("Google Drive authentication failed")
            return summary

        for local_path, content in zip(paths, contents):
            try:
                drive_path = self._drive_path(local_path)
            except ValueError:
                summary.skipped += 1
                summary.errors.append(f"Skipped empty path: {local_path!r}")
                continue

            result = self.sync_file(drive_path, content)
            if result == "created":
                summary.created += 1
            elif result == "updated":
                summary.updated += 1
            elif result == "unchanged":
                summary.unchanged += 1
            elif result is None:
                summary.failed += 1
                summary.errors.append(f"Drive sync failed: {drive_path}")
        return summary


def sync_local_paths(paths: List[str], contents: List[str]) -> SyncSummary:
    """Convenience function to synchronize local Markdown files to Google Drive."""
    sync = GoogleDriveSync()
    return sync.sync_local_paths(paths, contents)
