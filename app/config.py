from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Internship Application Tracker"
    database_url: str = "sqlite:///./email_tracker.db"
    frontend_url: str = "http://localhost:5173"
    google_client_secrets_file: str = "credentials.json"
    google_oauth_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    token_encryption_key: str | None = None
    classifier_provider: str = "laya"
    classifier_model_path: str = "artifacts/status_classifier.joblib"
    laya_model: str = "typed-decisions"
    laya_device: str | None = None
    laya_max_loaded: int = 1
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:latest"
    ollama_enabled: bool = True
    ml_high_confidence: float = 0.90
    ml_medium_confidence: float = 0.70

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
