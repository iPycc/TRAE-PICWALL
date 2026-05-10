from pathlib import Path
from uuid import uuid4
from fastapi import Request, UploadFile as FastUploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from server.core.config import get_settings
from server.core.error import api_error
from server.model.table import Asset, Upload, UploadPart, User
from server.schema.type import UploadCheckIn, UploadCompleteIn, UploadCreateIn
from server.service.asset import keep_extension
from server.service.log import write_log
from server.service.storage import active_storage
from server.store.local import append_files, save_upload, storage_path
from server.task.media import process_asset


ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ALLOWED_VIDEO = {"video/mp4", "video/quicktime"}
BLOCKED_EXTENSIONS = {".svg", ".exe", ".zip", ".bat", ".cmd", ".ps1"}


def validate_media(filename: str, mime: str, asset_type: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in BLOCKED_EXTENSIONS:
        raise api_error(400, "file_type_blocked", "This file type is not allowed")
    if asset_type == "image" and mime not in ALLOWED_IMAGE:
        raise api_error(400, "invalid_mime", "Invalid image MIME type")
    if asset_type == "video" and mime not in ALLOWED_VIDEO:
        raise api_error(400, "invalid_mime", "Invalid video MIME type")
    if not extension:
        extension = ".jpg" if asset_type == "image" else ".mp4"
    return extension.lstrip(".")


def infer_asset_type(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    raise api_error(400, "invalid_mime", "Only image and video uploads are allowed")


def find_hash_source(db: Session, storage_id: int, file_hash: str) -> Asset | None:
    return db.scalar(
        select(Asset)
        .where(Asset.storage_id == storage_id, Asset.hash == file_hash, Asset.status == "ready")
        .order_by(Asset.created_at.asc())
    )


def create_asset_from_payload(db: Session, payload: UploadCreateIn | UploadCheckIn, user: User, source: Asset | None = None) -> Asset:
    storage = active_storage(db)
    asset_type = payload.type or infer_asset_type(payload.mime)
    extension = validate_media(payload.filename, payload.mime, asset_type)
    title = keep_extension(payload.title or payload.filename, extension)
    asset = Asset(
        storage_id=storage.id,
        user_id=user.id,
        type=asset_type,
        status="ready" if source else "waiting",
        title=title,
        original_filename=payload.filename,
        extension=extension,
        mime=payload.mime,
        hash=payload.hash,
        size=payload.size,
        width=source.width if source else 0,
        height=source.height if source else 0,
        duration=source.duration if source else None,
        origin_key=source.origin_key if source else None,
        thumb_key=source.thumb_key if source else None,
        poster_key=source.poster_key if source else None,
    )
    db.add(asset)
    db.flush()
    return asset


def check_instant(db: Session, payload: UploadCheckIn, user: User, request: Request) -> dict:
    storage = active_storage(db)
    asset_type = payload.type or infer_asset_type(payload.mime)
    validate_media(payload.filename, payload.mime, asset_type)
    source = find_hash_source(db, storage.id, payload.hash)
    if not source:
        return {"instant": False}
    asset = create_asset_from_payload(db, payload, user, source)
    write_log(db, actor=user, action="upload", target_type="asset", target_id=asset.id, message="Instant upload", request=request)
    db.commit()
    return {"instant": True, "asset": asset}


def create_upload(db: Session, payload: UploadCreateIn, user: User, request: Request) -> dict:
    settings = get_settings()
    storage = active_storage(db)
    if storage.type != "local":
        raise api_error(501, "cos_not_implemented", "COS signing is not configured in this local build")
    asset_type = payload.type or infer_asset_type(payload.mime)
    validate_media(payload.filename, payload.mime, asset_type)
    source = find_hash_source(db, storage.id, payload.hash)
    if source:
        asset = create_asset_from_payload(db, payload, user, source)
        write_log(db, actor=user, action="upload", target_type="asset", target_id=asset.id, message="Instant upload", request=request)
        db.commit()
        return {
            "upload_id": "",
            "asset_id": asset.id,
            "storage_type": storage.type,
            "multipart": False,
            "part_size": settings.part_size,
            "concurrency": 4 if asset_type == "image" else 2,
            "upload_urls": [],
            "instant": True,
        }
    asset = create_asset_from_payload(db, payload, user)
    upload_id = f"up_{uuid4().hex}"
    multipart = payload.size > settings.multipart_threshold
    total_parts = max(1, (payload.size + settings.part_size - 1) // settings.part_size)
    upload = Upload(
        upload_id=upload_id,
        asset_id=asset.id,
        user_id=user.id,
        storage_id=storage.id,
        status="waiting",
        multipart=multipart,
        part_size=settings.part_size,
        total_parts=total_parts,
    )
    db.add(upload)
    db.commit()
    return {
        "upload_id": upload_id,
        "asset_id": asset.id,
        "storage_type": storage.type,
        "multipart": multipart,
        "part_size": settings.part_size,
        "concurrency": 4 if asset_type == "image" else 2,
        "upload_urls": [],
        "instant": False,
    }


def get_upload(db: Session, upload_id: str, user: User) -> Upload:
    upload = db.scalar(
        select(Upload)
        .options(joinedload(Upload.asset))
        .where(Upload.upload_id == upload_id)
    )
    if upload is None:
        raise api_error(404, "upload_not_found", "Upload not found")
    if upload.user_id != user.id:
        raise api_error(403, "forbidden", "Cannot access this upload")
    return upload


async def receive_part(db: Session, upload_id: str, part_number: int, file: FastUploadFile, user: User) -> dict:
    upload = get_upload(db, upload_id, user)
    if upload.status in ("completed", "canceled"):
        raise api_error(400, "upload_closed", "Upload is closed")
    upload.status = "uploading"
    upload.asset.status = "uploading"
    temp_key = f"temp/{upload.upload_id}/{part_number:06d}.part"
    size = await save_upload(file, temp_key)
    part = db.scalar(select(UploadPart).where(UploadPart.upload_id == upload.id, UploadPart.part_number == part_number))
    if part is None:
        part = UploadPart(upload_id=upload.id, part_number=part_number, etag=temp_key, size=size)
        db.add(part)
        upload.uploaded_parts += 1
    else:
        part.etag = temp_key
        part.size = size
    db.commit()
    return {"part_number": part_number, "etag": temp_key, "size": size}


def complete_upload(db: Session, upload_id: str, payload: UploadCompleteIn, user: User, request: Request) -> Asset:
    upload = get_upload(db, upload_id, user)
    asset = upload.asset
    if upload.multipart:
        parts = db.scalars(select(UploadPart).where(UploadPart.upload_id == upload.id).order_by(UploadPart.part_number.asc())).all()
        if len(parts) < upload.total_parts:
            raise api_error(400, "parts_missing", "Not all parts were uploaded")
        origin_key = f"origin/{asset.id}.{asset.extension}"
        append_files([storage_path(part.etag) for part in parts], storage_path(origin_key))
    else:
        part = db.scalar(select(UploadPart).where(UploadPart.upload_id == upload.id).order_by(UploadPart.part_number.asc()))
        if part is None:
            raise api_error(400, "file_missing", "Uploaded file is missing")
        origin_key = f"origin/{asset.id}.{asset.extension}"
        append_files([storage_path(part.etag)], storage_path(origin_key))
    asset.origin_key = origin_key
    asset.status = "uploaded"
    upload.status = "completed"
    try:
        process_asset(db, asset)
    except Exception as exc:
        write_log(db, actor=user, action="upload_failed", target_type="asset", target_id=asset.id, message=str(exc), request=request)
        raise
    write_log(db, actor=user, action="upload", target_type="asset", target_id=asset.id, request=request)
    db.commit()
    return asset


def cancel_upload(db: Session, upload_id: str, user: User) -> None:
    upload = get_upload(db, upload_id, user)
    upload.status = "canceled"
    upload.asset.status = "failed"
    db.commit()

