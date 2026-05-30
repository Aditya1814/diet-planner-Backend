from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_jwt_secret: str = ""
    gemini_credentials_path: str = ""
    gemini_project_id: str = ""
    gemini_region: str = "us-central1"
    gemini_model: str = "gemini-2.5-pro"
    google_search_api_key: str = ""
    google_search_engine_id: str = ""

    # CORS
    frontend_origin: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
