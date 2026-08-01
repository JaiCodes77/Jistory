from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
IMPORTS_DIR = DATA_DIR / "imports"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Jistory"
    app_version: str = "0.1.0"
    debug: bool = True
    api_prefix: str = "/api"

    # Comma-separated origins, e.g. "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    database_url: str = f"sqlite:///{DATA_DIR / 'jistory.db'}"

    # Maximum ChatGPT export ZIP size (MB)
    max_import_size_mb: int = 500

    imports_dir: str = str(IMPORTS_DIR)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_import_bytes(self) -> int:
        return self.max_import_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
