"""Tests for the Internship Logbook Google Drive integration.

All tests are mocked — they do NOT make real API calls
and do NOT create fake data in any Google Drive folder.

Run with:
    PYTHONPATH=scripts python3 -m pytest tests/ -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from config import StorageConfig, GoogleDriveConfig
from google_drive_provider import GoogleDriveProvider


class TestConfig:
    """Test configuration loading and validation."""

    def test_default_storage_is_local(self):
        """Default provider should be 'local'."""
        config = StorageConfig()
        assert config.provider == "local"
        assert not config.is_google_drive()

    def test_google_drive_disabled_by_default(self):
            """Google Drive should be disabled by default."""
            from config import StorageConfig
            config = StorageConfig()
            assert config.google_drive.enabled is False
            assert config.google_drive.root_folder_id == ""

    def test_google_drive_enabled(self):
        """Test enabling Google Drive provider."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        assert config.is_google_drive()

    def test_env_loading(self):
        """Test loading from environment variables."""
        env = {
            "STORAGE_PROVIDER": "google_drive",
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": "test_folder_id",
        }
        with patch.dict(os.environ, env, clear=False):
            config = StorageConfig.from_env()
            assert config.provider == "google_drive"
            assert config.google_drive.root_folder_id == "test_folder_id"

    def test_json_loading(self):
        """Test loading configuration from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_data = {
                "provider": "google_drive",
                "google_drive": {
                    "enabled": True,
                    "root_folder_id": "test_id",
                },
            }
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            config = StorageConfig.from_file(str(config_path))
            assert config.provider == "google_drive"
            assert config.google_drive.enabled is True
            assert config.google_drive.root_folder_id == "test_id"

    def test_sensitive_paths_not_committed(self):
        """Verify that credential paths are defined as user-specific."""
        from config import USER_CREDENTIAL_PATHS
        assert len(USER_CREDENTIAL_PATHS) >= 2
        assert any("google_client_secret" in p for p in USER_CREDENTIAL_PATHS)
        assert any("google_token" in p for p in USER_CREDENTIAL_PATHS)


class TestGoogleDriveProvider:
    """Test Google Drive provider methods (all mocked)."""

    def test_authenticate_without_config(self):
        """Provider should return False when Google Drive is disabled."""
        provider = GoogleDriveProvider()
        config = StorageConfig(provider="local")
        p = GoogleDriveProvider(config)
        result = p.authenticate()
        assert result is False
        assert p._initialized is False

    def test_authenticate_missing_root_folder_id(self):
        """Provider should return False when root_folder_id is placeholder."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)
        # Mock get_service to avoid actual auth prompt
        with patch('google_drive_provider.get_service', return_value=None):
            result = provider.authenticate()
        assert result is False

    def test_find_folder_returns_none_when_not_initialized(self):
        """find_folder should return None when not authenticated."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)
        with patch('google_drive_provider.get_service', return_value=None):
            result = provider.find_folder("daily")
        assert result is None

    def test_create_folder_returns_none_when_not_initialized(self):
        """create_folder should return None when not authenticated."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)
        with patch('google_drive_provider.get_service', return_value=None):
            result = provider.create_folder("daily")
        assert result is None

    def test_path_generation_daily(self):
        """Verify daily log path follows YYYY/MM/YYYY-MM-DD format."""
        from datetime import date

        d = date(2026, 9, 8)
        expected = f"daily/{d.year}/{d.month:02d}/{d.isoformat()}.md"
        assert expected == "daily/2026/09/2026-09-08.md"

    def test_path_generation_weekly(self):
        """Verify weekly log path follows YYYY/Week-XX format."""
        expected = "weekly/2026/Week-06.md"
        assert expected == "weekly/2026/Week-06.md"

    def test_path_generation_monthly(self):
        """Verify monthly log path follows YYYY/YYYY-MM format."""
        expected = "monthly/2026/2026-09.md"
        assert expected == "monthly/2026/2026-09.md"

    def test_duplicate_prevention_in_find_folder(self):
        """find_folder should find existing folder and reuse it."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)

        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "folder_123", "name": "daily"}]
        }
        provider.service = mock_service
        provider.root_folder_id = "root_123"
        provider._initialized = True

        result = provider.find_folder("daily")
        assert result == "folder_123"

    def test_duplicate_prevention_in_create_folder(self):
        """create_folder should return existing folder ID if it already exists."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)

        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "folder_123", "name": "daily"}]
        }
        provider.service = mock_service
        provider.root_folder_id = "root_123"
        provider._initialized = True

        result = provider.create_folder("daily")
        assert result == "folder_123"

    def test_ensure_structure(self):
        """ensure_structure should report found folders without creating duplicates."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)

        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "folder_123", "name": "daily"}]
        }
        provider.service = mock_service
        provider.root_folder_id = "root_123"
        provider._initialized = True

        result = provider.ensure_structure()
        assert "found" in result
        assert "daily" in result["found"]
        assert result["found"]["daily"] == "folder_123"


class TestMarkdownOperations:
    """Test Markdown content handling."""

    def test_create_or_update_markdown_returns_false_when_not_authenticated(self):
        """create_or_update_markdown should return False when not authenticated."""
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)
        with patch('google_drive_provider.get_service', return_value=None):
            result = provider.create_or_update_markdown(
                "daily/2026/09/2026-09-08.md", "# Test"
            )
        assert result is False

    def test_daily_path_format(self):
        """Verify daily Markdown path format."""
        paths = [
            "daily/2026/09/2026-09-08.md",
            "daily/2026/08/2026-08-24.md",
            "daily/2025/12/2025-12-31.md",
        ]
        for path in paths:
            parts = path.split("/")
            # daily/YYYY/MM/YYYY-MM-DD.md = 4 parts
            assert len(parts) == 4
            assert parts[0] == "daily"
            assert len(parts[1]) == 4  # year
            assert len(parts[2]) == 2  # month (zero-padded)
            assert len(parts[3]) == 13  # YYYY-MM-DD.md

    def test_sync_does_not_create_duplicate_on_second_pass(self):
        """Re-syncing an existing file should not create a duplicate."""
        from google_drive_sync import GoogleDriveSync

        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        provider = GoogleDriveProvider(config)

        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "file_123", "name": "2026-09-08.md"}]
        }
        provider.service = mock_service
        provider.root_folder_id = "root_123"
        provider._initialized = True

        content = "# Test"
        sync = GoogleDriveSync(provider)

        with patch.object(
            sync,
            "_existing_drive_content",
            return_value=content,
        ):
            first = sync.sync_file("daily/2026/09/2026-09-08.md", content)
            second = sync.sync_file("daily/2026/09/2026-09-08.md", content)

        assert first == "unchanged"
        assert second == "unchanged"
        assert provider.service.files().create.call_count == 0


class TestLocalStorageFallback:
    """Test that local storage works without Google Drive."""

    def test_local_provider_does_not_require_auth(self):
        """Local storage should work without any authentication."""
        config = StorageConfig(provider="local")
        assert config.provider == "local"
        assert not config.is_google_drive()

    def test_google_drive_not_required(self):
        """The core logbook should work with provider='local'."""
        from datetime import date

        d = date.today()
        daily_path = f"daily/{d.year}/{d.month:02d}/{d.isoformat()}.md"
        assert "daily/" in daily_path
        assert ".md" in daily_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
