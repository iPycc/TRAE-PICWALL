from pathlib import Path
from uuid import uuid4

from fastapi import Request, UploadFile as FastUploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from server.core.config import get_settings
from server.core.error import api_error
from server.model.table import Asset, Upload, UploadPart, User
from server.schema.type import UploadCompleteIn, UploadCreateIn
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


def create_asset_from_payload(
    db: Session,
    payload: UploadCreateIn,
    user: User,
) -> Asset:
    storage = active_storage(db)
    asset_type = payload.type
    extension = validate_media(payload.filename, payload.mime, asset_type)
    title = keep_extension(payload.title or payload.filename, extension)
    asset = Asset(
        storage_id=storage.id,
        user_id=user.id,
        type=asset_type,
        status="waiting",
        title=title,
        original_filename=payload.filename,
        extension=extension,
        mime=payload.mime,
        hash=f"upload:{uuid4().hex}",
        size=payload.size,
        width=0,
        height=0,
    )
    db.add(asset)
    db.flush()
    return asset


def create_upload(db: Session, payload: UploadCreateIn, user: User, request: Request) -> dict:
    settings = get_settings()
    storage = active_storage(db)
    if storage.type != "local":
        raise api_error(501, "cos_not_implemented", "COS signing is not configured in this local build")
    asset_type = payload.type
    validate_media(payload.filename, payload.mime, asset_type)
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
        parts = db.scalars(
            select(UploadPart).where(UploadPart.upload_id == upload.id).order_by(UploadPart.part_number.asc())
        ).all()
        if len(parts) < upload.total_parts:
            raise api_error(400, "parts_missing", "Not all parts were uploaded")
        origin_key = f"origin/{asset.id}.{asset.extension}"
        append_files([storage_path(part.etag) for part in parts], storage_path(origin_key))
    else:
        part = db.scalar(
            select(UploadPart).where(UploadPart.upload_id == upload.id).order_by(UploadPart.part_number.asc())
        )
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
        write_log(
            db,
            actor=user,
            action="upload_failed",
            target_type="asset",
            target_id=asset.id,
            message=str(exc),
            request=request,
        )
        raise
    write_log(db, actor=user, action="upload", target_type="asset", target_id=asset.id, request=request)
    db.commit()
    return asset


def cancel_upload(db: Session, upload_id: str, user: User) -> None:
    upload = get_upload(db, upload_id, user)
    upload.status = "canceled"
    upload.asset.status = "failed"
    db.commit()
