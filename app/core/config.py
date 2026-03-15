"""
Application Settings Configuration
Using Pydantic BaseSettings for automatic environment variable loading

Note: This configuration requires a .env file in the project root.
Copy .env.example to .env and configure the variables before running the application.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Loads from .env file with HABITARE_ prefix.
    Example: HABITARE_DATABASE_URL in .env becomes settings.database_url
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_prefix='HABITARE_',
        case_sensitive=False,
        extra='ignore'  # Ignore extra fields in .env for forward compatibility
    )

    # Database Configuration
    database_url: str
    redis_url: str

    # Security & JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Fernet Encryption (for TOTP secrets)
    fernet_key: str = "change-me-generate-with-fernet"

    # CORS Configuration
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Environment
    environment: str = "development"
    debug: bool = True

    # Database Pool Configuration
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_echo: bool = False


# Global settings instance
settings = Settings()
