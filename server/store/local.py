from pathlib import Path
import shutil
from fastapi import UploadFile
from server.core.config import get_settings


settings = get_settings()


def storage_path(key: str) -> Path:
    safe = key.replace("\\", "/").lstrip("/")
    path = settings.storage_root / safe
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def remove_key(key: str | None) -> None:
    if not key:
        return
    path = storage_path(key)
    if path.exists():
        path.unlink()


async def save_upload(file: UploadFile, key: str) -> int:
    path = storage_path(key)
    size = 0
    with path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return size


def append_files(parts: list[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        for part in parts:
            with part.open("rb") as src:
                shutil.copyfileobj(src, out)

