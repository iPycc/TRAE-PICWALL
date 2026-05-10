from pathlib import Path
import subprocess
import shutil
from sqlalchemy.orm import Session
from server.model.table import Asset
from server.store.local import storage_path


def ffmpeg_exe() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _try_image(asset: Asset) -> None:
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError:
        return
    if not asset.origin_key:
        return
    src = storage_path(asset.origin_key)
    if not src.exists():
        return
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        asset.width, asset.height = img.size
        img.thumbnail((1200, 1200))
        thumb_key = f"thumb/{asset.id}.webp"
        thumb_path = storage_path(thumb_key)
        img.save(thumb_path, "WEBP", quality=82, method=6)
        asset.thumb_key = thumb_key


def _try_video(asset: Asset) -> None:
    if not asset.origin_key:
        return
    src = storage_path(asset.origin_key)
    if not src.exists():
        return
    executable = ffmpeg_exe()
    if not executable:
        return
    poster_key = f"poster/{asset.id}.jpg"
    poster_path = storage_path(poster_key)
    try:
        subprocess.run(
            [
                executable,
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(poster_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if poster_path.exists():
            asset.poster_key = poster_key
    except (FileNotFoundError, subprocess.CalledProcessError):
        return


def process_asset(db: Session, asset: Asset) -> None:
    asset.status = "processing"
    db.flush()
    try:
        if asset.type == "image":
            _try_image(asset)
        elif asset.type == "video":
            _try_video(asset)
        asset.status = "ready"
    except Exception:
        asset.status = "failed"
        raise
