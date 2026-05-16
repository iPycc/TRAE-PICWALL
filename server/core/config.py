from functools import lru_cache
import configparser
import secrets
import string
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONF_PATH = PROJECT_ROOT / "conf.ini"


def _random_jwt_secret(length: int = 50) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _ensure_conf_ini() -> dict[str, str]:
    parser = configparser.ConfigParser()

    if CONF_PATH.exists():
        parser.read(CONF_PATH, encoding="utf-8")
    else:
        parser["app"] = {
            "app_name": "TRAE Friends@City PIC-WALL",
            "host": "0.0.0.0",
            "port": "1309",
            "web_base_path": "",
            "api_prefix": "/api/v1",
            "cors_origins": "http://localhost:5273,http://127.0.0.1:5273",
        }
        parser["db"] = {
            "database_url": "mysql+pymysql://root:password@127.0.0.1:3306/picwall?charset=utf8mb4",
        }
        parser["auth"] = {
            "jwt_secret": "",
            "jwt_algorithm": "HS256",
            "access_token_minutes": "15",
            "refresh_token_days": "7",
        }
        parser["storage"] = {
            "storage_root": "storage",
            "storage_secret_key": "",
            "cos_signed_url_seconds": "900",
            "cos_thumb_max_size": "480",
            "cos_thumb_quality": "80",
            "cos_cors_origins": "",
        }
        with CONF_PATH.open("w", encoding="utf-8") as f:
            parser.write(f)

    if "auth" not in parser:
        parser["auth"] = {}

    jwt_secret = (parser["auth"].get("jwt_secret") or "").strip()
    if not jwt_secret:
        parser["auth"]["jwt_secret"] = _random_jwt_secret(50)
        with CONF_PATH.open("w", encoding="utf-8") as f:
            parser.write(f)

    def pick(section: str, key: str) -> str | None:
        if section not in parser:
            return None
        value = (parser[section].get(key) or "").strip()
        return value or None

    values: dict[str, str] = {}
    for section, keys in {
        "app": ["app_name", "host", "port", "web_base_path", "api_prefix", "cors_origins"],
        "db": ["database_url"],
        "auth": ["jwt_secret", "jwt_algorithm", "access_token_minutes", "refresh_token_days"],
        "storage": [
            "storage_root",
            "storage_secret_key",
            "cos_signed_url_seconds",
            "cos_thumb_max_size",
            "cos_thumb_quality",
            "cos_cors_origins",
        ],
    }.items():
        for key in keys:
            value = pick(section, key)
            if value is not None:
                values[key] = value

    return values


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "TRAE Friends@City PIC-WALL"
    api_prefix: str = "/api/v1"
    web_base_path: str = ""
    host: str = "0.0.0.0"
    port: int = 1309
    database_url: str = "mysql+pymysql://root:password@127.0.0.1:3306/picwall?charset=utf8mb4"
    jwt_secret: str = "change-me-in-production-with-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    storage_root: Path = Path("storage")
    public_base_url: str = ""
    multipart_threshold: int = 200 * 1024 * 1024
    part_size: int = 8 * 1024 * 1024
    cors_origins: str = "http://localhost:5273,http://127.0.0.1:5273"
    storage_secret_key: str | None = None
    cos_signed_url_seconds: int = 15 * 60
    cos_thumb_max_size: int = 480
    cos_thumb_quality: int = 80
    cos_cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cos_cors_origin_list(self) -> list[str]:
        origins = self.cos_cors_origins or self.cors_origins
        return [origin.strip() for origin in origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings(**_ensure_conf_ini())
