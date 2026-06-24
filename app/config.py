from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic-settings reads values from:
    1. Environment variables (highest priority)
    2. .env file (if it exists)
    3. Default values defined here (lowest priority)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "DarkAtlas Asset Management"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/darkatlas"

    # Authentication
    API_KEY: str = "changeme"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000


# Singleton instance — import this everywhere
settings = Settings()
