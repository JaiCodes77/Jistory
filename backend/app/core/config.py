from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
IMPORTS_DIR = DATA_DIR / "imports"
SETTINGS_PATH = DATA_DIR / "settings.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Jistory"
    app_version: str = "1.0.0"
    debug: bool = True
    api_prefix: str = "/api"

    cors_origins: str = "http://localhost:3000"

    database_url: str = f"sqlite:///{DATA_DIR / 'jistory.db'}"

    max_import_size_mb: int = 500
    imports_dir: str = str(IMPORTS_DIR)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2

    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    retrieval_limit: int = 8
    ask_max_history_turns: int = 8

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_import_bytes(self) -> int:
        return self.max_import_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
