"""Configuration for the Internship Logbook storage providers.

This module provides the configuration layer that allows the core
Internship Logbook logic to work with local storage, Google Drive,
or local Markdown storage without depending on any of them directly.

User-specific configuration (credentials, folder IDs) lives in
~/.hermes/ and is never committed to any public repository.

Environment variables:
    STORAGE_PROVIDER        - "local" or "google_drive"
    GOOGLE_DRIVE_ROOT_FOLDER_ID - Google Drive root folder ID
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GoogleDriveConfig:
    """Google Drive-specific configuration.

    All sensitive fields (client_secret, token) are stored in
    ~/.hermes/ and never committed to the public repository.
    """

    enabled: bool = False
    root_folder_id: str = "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID"
    credentials_path: str = ""  # Defaults to ~/.hermes/google_client_secret.json
    token_path: str = ""        # Defaults to ~/.hermes/google_token.json

    def __post_init__(self):
        if not self.credentials_path:
            self.credentials_path = str(
                Path.home() / ".hermes" / "google_client_secret.json"
            )
        if not self.token_path:
            self.token_path = str(
                Path.home() / ".hermes" / "google_token.json"
            )


@dataclass
class StorageConfig:
    """Top-level storage configuration."""

    provider: str = "local"  # "local" | "google_drive"
    google_drive: GoogleDriveConfig = field(default_factory=GoogleDriveConfig)

    def is_google_drive(self) -> bool:
        return self.provider == "google_drive" and self.google_drive.enabled

    @classmethod
    def from_env(cls) -> "StorageConfig":
        """Load configuration from environment variables."""
        provider = os.environ.get("STORAGE_PROVIDER", "local")
        config = cls(provider=provider)

        if provider == "google_drive":
            config.google_drive.enabled = True
            config.google_drive.root_folder_id = os.environ.get(
                "GOOGLE_DRIVE_ROOT_FOLDER_ID",
                config.google_drive.root_folder_id,
            )

        return config

    @classmethod
    def from_file(cls, path: str) -> "StorageConfig":
        """Load configuration from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            provider=data.get("provider", "local"),
            google_drive=GoogleDriveConfig(
                enabled=data.get("google_drive", {}).get("enabled", False),
                root_folder_id=data.get("google_drive", {}).get(
                    "root_folder_id", "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID"
                ),
                credentials_path=data.get("google_drive", {}).get(
                    "credentials_path", ""
                ),
                token_path=data.get("google_drive", {}).get("token_path", ""),
            ),
        )


def get_config() -> StorageConfig:
    """Get the current storage configuration."""
    config_path = os.environ.get("STORAGE_CONFIG_PATH")
    if config_path and os.path.exists(config_path):
        return StorageConfig.from_file(config_path)
    return StorageConfig.from_env()


# User-specific paths that must never be committed
USER_CREDENTIAL_PATHS = [
    str(Path.home() / ".hermes" / "google_client_secret.json"),
    str(Path.home() / ".hermes" / "google_token.json"),
]

# Safe paths that can be committed to the public repo
REPO_CONFIG_PATHS = [
    str(Path(__file__).parent.parent / "scripts" / "config.json"),
]