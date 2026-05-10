from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "TRAE Friends@City PIC-WALL"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 1309
    database_url: str = "sqlite:///./picwall.db"
    jwt_secret: str = "change-me-in-production-with-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    storage_root: Path = Path("storage")
    public_base_url: str = ""
    multipart_threshold: int = 200 * 1024 * 1024
    part_size: int = 8 * 1024 * 1024
    cors_origins: str = "http://localhost:5273,http://127.0.0.1:5273"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
