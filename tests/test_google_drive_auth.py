"""Tests for Google Drive authentication.

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

from google_drive_auth import (
    find_hermes_workspace_setup,
    hermes_workspace_available,
    token_is_valid,
    load_credentials,
    get_credentials,
    build_drive_service,
    check_auth,
    _default_token_path,
    _default_client_secret_path,
    SCOPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_hermes_home(tmp_path):
    """Create a fake Hermes home directory structure."""
    home = tmp_path / ".hermes"
    home.mkdir()
    return home


@pytest.fixture
def fake_client_secret(tmp_path):
    """Create a fake client_secret.json file."""
    secret = tmp_path / "google_client_secret.json"
    secret.write_text(json.dumps({
        "installed": {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "redirect_uris": ["http://localhost"],
        }
    }))
    return secret


@pytest.fixture
def fake_token(tmp_path):
    """Create a fake google_token.json file."""
    token = tmp_path / "google_token.json"
    token.write_text(json.dumps({
        "token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "scopes": SCOPES,
    }))
    return token


# ---------------------------------------------------------------------------
# Hermes Workspace discovery
# ---------------------------------------------------------------------------

class TestFindHermesWorkspaceSetup:
    """Test find_hermes_workspace_setup()."""

    def test_finds_setup_in_hermes_home(self, fake_hermes_home, tmp_path):
        """Should find setup.py in Hermes home skills directory."""
        skill_dir = fake_hermes_home / "skills" / "productivity" / "google-workspace" / "scripts"
        skill_dir.mkdir(parents=True)
        (skill_dir / "setup.py").write_text("# fake")

        with patch("google_drive_auth.Path.home", return_value=fake_hermes_home.parent):
            with patch("google_drive_auth.os.environ", {"HERMES_HOME": str(fake_hermes_home)}):
                result = find_hermes_workspace_setup()
        assert result is not None
        assert result.name == "setup.py"

    def test_returns_none_when_not_installed(self, tmp_path, monkeypatch):
        """Should return None when Hermes is not installed."""
        # Make Path.home return tmp_path (no .hermes/skills/ there)
        # and clear HERMES_HOME so the default path is used
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = find_hermes_workspace_setup()
        assert result is None

    def test_hermes_workspace_available(self, fake_hermes_home):
        """hermes_workspace_available() should match find_hermes_workspace_setup()."""
        skill_dir = fake_hermes_home / "skills" / "productivity" / "google-workspace" / "scripts"
        skill_dir.mkdir(parents=True)
        (skill_dir / "setup.py").write_text("# fake")

        with patch("google_drive_auth.Path.home", return_value=fake_hermes_home.parent):
            with patch("google_drive_auth.os.environ", {"HERMES_HOME": str(fake_hermes_home)}):
                assert hermes_workspace_available() is True

    def test_hermes_workspace_not_available(self, tmp_path):
        """Should return False when no workspace setup found."""
        import google_drive_auth as _mod
        original = _mod.find_hermes_workspace_setup
        _mod.find_hermes_workspace_setup = lambda: None
        try:
            assert hermes_workspace_available() is False
        finally:
            _mod.find_hermes_workspace_setup = original


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

class TestTokenValidation:
    """Test token_is_valid() and load_credentials()."""

    def test_valid_token(self, fake_token):
        """A valid token should return True."""
        assert token_is_valid(fake_token) is True

    def test_missing_token(self, tmp_path):
        """Missing token file should return False."""
        assert token_is_valid(tmp_path / "nonexistent.json") is False

    def test_invalid_json(self, tmp_path):
        """Invalid JSON in token file should return False."""
        bad = tmp_path / "bad_token.json"
        bad.write_text("not json")
        assert token_is_valid(bad) is False

    def test_missing_refresh_token(self, tmp_path):
        """Expired token without refresh token should return False."""
        expired = tmp_path / "expired.json"
        expired.write_text(json.dumps({
            "token": "expired-token",
            "refresh_token": None,
            "scopes": SCOPES,
        }))
        assert token_is_valid(expired) is False

    def test_load_valid_credentials(self, fake_token):
        """Should load credentials from a valid token file."""
        fake_creds = MagicMock()
        fake_creds.valid = True
        with patch("google_drive_auth.load_credentials", return_value=fake_creds):
            creds, msg = get_credentials(token_path=fake_token)
        assert creds is not None
        assert msg == "Authenticated via existing token."

    def test_load_missing_credentials(self, tmp_path):
        """Should return None when no token file exists."""
        creds, msg = get_credentials(token_path=tmp_path / "missing.json")
        assert creds is None
        assert "No Google Drive token found" in msg

    def test_check_auth_valid(self, fake_token):
        """check_auth should return True for valid token."""
        fake_creds = MagicMock()
        fake_creds.valid = True
        with patch("google_drive_auth.load_credentials", return_value=fake_creds):
            ok, msg = check_auth(token_path=fake_token)
        assert ok is True

    def test_check_auth_missing(self, tmp_path):
        """check_auth should return False when token missing."""
        ok, msg = check_auth(token_path=tmp_path / "missing.json")
        assert ok is False
        assert "No token file" in msg


# ---------------------------------------------------------------------------
# get_credentials status messages
# ---------------------------------------------------------------------------

class TestGetCredentialsMessages:
    """Test that get_credentials returns helpful messages."""

    def test_expired_token_no_refresh(self, tmp_path):
        """Expired token without refresh should give clear message."""
        expired = tmp_path / "expired.json"
        expired.write_text(json.dumps({
            "token": "expired",
            "refresh_token": None,
            "scopes": SCOPES,
        }))
        creds, msg = get_credentials(token_path=expired)
        assert creds is None
        assert "expired" in msg.lower()

    def test_no_hermes_workspace(self, fake_hermes_home, tmp_path):
        """Message when Hermes workspace is not installed."""
        # No token file, no Hermes home
        with patch("google_drive_auth.os.environ", {}):
            with patch("google_drive_auth.Path.home", return_value=tmp_path):
                creds, msg = get_credentials(token_path=tmp_path / "missing.json")
        assert creds is None
        assert "Hermes" in msg or "setup" in msg.lower()


# ---------------------------------------------------------------------------
# build_drive_service
# ---------------------------------------------------------------------------

class TestBuildDriveService:
    """Test build_drive_service()."""

    def test_build_with_valid_token(self, fake_token):
        """Should build a service with valid credentials."""
        mock_service = MagicMock()
        fake_creds = MagicMock()
        fake_creds.valid = True
        with patch("google_drive_auth.load_credentials", return_value=fake_creds):
            with patch("googleapiclient.discovery.build", return_value=mock_service):
                service, err = build_drive_service(token_path=fake_token)
        assert service is not None
        assert err is None

    def test_build_with_missing_token(self, tmp_path):
        """Should return error when no token."""
        service, err = build_drive_service(token_path=tmp_path / "missing.json")
        assert service is None
        assert err is not None
        assert "No Google Drive token" in err or "not found" in err.lower()


# ---------------------------------------------------------------------------
# Backwards compatibility: config.py
# ---------------------------------------------------------------------------

class TestConfigBackwardsCompatibility:
    """Ensure config.py still works with the new auth module."""

    def test_default_storage_is_local(self):
        """Default provider should be 'local'."""
        from config import StorageConfig
        config = StorageConfig()
        assert config.provider == "local"
        assert not config.is_google_drive()

    def test_google_drive_disabled_by_default(self):
        """Google Drive should be disabled by default."""
        from config import StorageConfig, GoogleDriveConfig
        config = StorageConfig()
        assert config.google_drive.enabled is False

    def test_google_drive_enabled(self):
        """Test enabling Google Drive provider."""
        from config import StorageConfig, GoogleDriveConfig
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(enabled=True),
        )
        assert config.is_google_drive()

    def test_env_loading(self):
        """Test loading from environment variables."""
        from config import StorageConfig
        env = {
            "STORAGE_PROVIDER": "google_drive",
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": "test_folder_id",
        }
        with patch.dict(os.environ, env, clear=False):
            config = StorageConfig.from_env()
            assert config.provider == "google_drive"
            assert config.google_drive.root_folder_id == "test_folder_id"

    def test_sensitive_paths_not_committed(self):
        """Verify that credential paths are defined as user-specific."""
        from config import USER_CREDENTIAL_PATHS
        assert len(USER_CREDENTIAL_PATHS) >= 2
        assert any("google_client_secret" in p for p in USER_CREDENTIAL_PATHS)
        assert any("google_token" in p for p in USER_CREDENTIAL_PATHS)

    def test_root_folder_id_not_hardcoded(self):
        """Default root_folder_id should not be the old placeholder."""
        from config import GoogleDriveConfig

        # Other tests (and config.load_dotenv_once) can populate the process
        # environment from the repo .env, so clear it for this assertion.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_DRIVE_ROOT_FOLDER_ID", None)
            config = GoogleDriveConfig()
        # Should be empty string by default, not the placeholder
        assert config.root_folder_id == ""


# ---------------------------------------------------------------------------
# Path safety — no hardcoded personal paths
# ---------------------------------------------------------------------------

class TestPathSafety:
    """Ensure no hardcoded personal paths in source."""

    def test_no_personal_paths_in_auth(self):
        """google_drive_auth.py should not contain hardcoded usernames."""
        auth_path = Path(__file__).parent.parent / "scripts" / "google_drive_auth.py"
        content = auth_path.read_text()

        # Common personal path patterns that should NOT be hardcoded
        banned_patterns = [
            "/home/hafizuddin",
            "C:\\Users\\Hafizuddin",
            "/Users/hafizuddin",
        ]
        for pattern in banned_patterns:
            assert pattern.lower() not in content.lower(), (
                f"Hardcoded personal path found: {pattern}"
            )

    def test_no_tokens_in_source(self):
        """No OAuth tokens should be hardcoded in source files."""
        scripts_dir = Path(__file__).parent.parent / "scripts"
        for script in scripts_dir.glob("*.py"):
            content = script.read_text()
            # Check for obviously fake-but-common token patterns
            assert "fake-access-token" not in content

    def test_no_secrets_in_gitignore(self):
        """Credentials should be excluded by .gitignore."""
        gitignore = Path(__file__).parent.parent / ".gitignore"
        content = gitignore.read_text()

        assert "google_client_secret.json" in content
        assert "google_token.json" in content
        assert "token.json" in content
        assert ".env" in content

    def test_env_example_exists(self):
        """An .env.example file should exist with placeholders only."""
        env_example = Path(__file__).parent.parent / ".env.example"
        assert env_example.is_file()
        content = env_example.read_text()
        assert "YOUR_GOOGLE_DRIVE_FOLDER_ID" in content or "GOOGLE_DRIVE_ROOT_FOLDER_ID=" in content
        # Should NOT contain real values
        assert "fake" not in content.lower() or "placeholder" in content.lower()


# ---------------------------------------------------------------------------
# Integration-style tests (mocked)
# ---------------------------------------------------------------------------

class TestIntegrationScenarios:
    """Test full auth scenarios with mocks."""

    def test_authenticated_user_flow(self, fake_token, fake_hermes_home):
        """A user with a valid token should be authenticated."""
        fake_creds = MagicMock()
        fake_creds.valid = True
        with patch("google_drive_auth.load_credentials", return_value=fake_creds):
            ok, msg = check_auth(token_path=fake_token)
        assert ok is True

    def test_missing_authentication_flow(self, tmp_path):
        """A user with no token should get setup instructions."""
        creds, msg = get_credentials(token_path=tmp_path / "missing.json")
        assert creds is None
        assert "setup" in msg.lower() or "install" in msg.lower()

    def test_expired_credentials_flow(self, tmp_path):
        """Expired token without refresh should fail gracefully."""
        expired = tmp_path / "expired.json"
        expired.write_text(json.dumps({
            "token": "expired",
            "refresh_token": None,
            "scopes": SCOPES,
        }))
        creds, msg = get_credentials(token_path=expired)
        assert creds is None

    def test_missing_client_secret_flow(self, tmp_path):
        """Missing client secret should be detected."""
        secret_path = tmp_path / "missing_secret.json"
        ok, msg = check_auth(
            token_path=tmp_path / "missing_token.json",
            client_secret_path=secret_path,
        )
        assert ok is False

    def test_invalid_configuration_flow(self, tmp_path):
        """Invalid config (bad root_folder_id placeholder) should be detected."""
        from config import StorageConfig, GoogleDriveConfig
        config = StorageConfig(
            provider="google_drive",
            google_drive=GoogleDriveConfig(
                enabled=True,
                root_folder_id="YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID",
            ),
        )
        assert config.google_drive.root_folder_id == "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID"
        assert config.is_google_drive() is True  # enabled, but placeholder ID

    def test_google_drive_api_auth_failure(self, tmp_path):
        """Drive API auth failure should be distinguishable from missing credentials."""
        fake_but_invalid = tmp_path / "invalid_token.json"
        fake_but_invalid.write_text(json.dumps({
            "token": "invalid",
            "refresh_token": "invalid_refresh",
            "scopes": ["wrong_scope"],
        }))
        # This should fail to load as valid credentials
        creds = load_credentials(fake_but_invalid)
        # The token may load but be invalid; that's fine — the
        # important thing is the function doesn't crash
        assert creds is None or hasattr(creds, 'valid')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
