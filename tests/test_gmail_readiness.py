import json

from cryptography.fernet import Fernet

from app.config import Settings
from app.services.gmail import gmail_readiness


REDIRECT = "http://localhost:8001/api/auth/google/callback"


def settings(path, key: str | None = None) -> Settings:
    return Settings(
        google_client_secrets_file=str(path),
        google_oauth_redirect_uri=REDIRECT,
        token_encryption_key=key,
    )


def test_readiness_explains_missing_redirect(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "web": {"client_id": "id", "client_secret": "secret", "redirect_uris": []}
    }), encoding="utf-8")
    result = gmail_readiness(settings(path, Fernet.generate_key().decode()))
    assert result["ready"] is False
    assert result["redirect_registered"] is False
    assert any("Register and download" in issue for issue in result["issues"])


def test_readiness_accepts_complete_web_client(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "web": {"client_id": "id", "client_secret": "secret", "redirect_uris": [REDIRECT]}
    }), encoding="utf-8")
    result = gmail_readiness(settings(path, Fernet.generate_key().decode()))
    assert result["ready"] is True
    assert result["issues"] == []
