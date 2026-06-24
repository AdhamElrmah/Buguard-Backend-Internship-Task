from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project root directory (one level up from app/config.py)
# This ensures .env is found regardless of where uvicorn is launched from.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic-settings reads values from:
    1. Environment variables (highest priority)
    2. .env file (if it exists)
    3. Default values defined here (lowest priority)
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "DarkAtlas Asset Management"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/darkatlas"

    # Authentication
    API_KEY: str = "changeme"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000


# Singleton instance — import this everywhere
settings = Settings()
