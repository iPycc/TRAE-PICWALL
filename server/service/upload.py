import re
from os import path
from pathlib import Path
from uuid import uuid4

from fastapi import Request, UploadFile as FastUploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from server.core.config import get_settings
from server.core.error import api_error
from server.model.table import Asset, Storage, Upload, UploadPart, User
from server.schema.type import UploadCompleteIn, UploadCreateIn
from server.service.asset import keep_extension
from server.service.log import write_log
from server.service.storage import active_storage
from server.store.cos import (
    abort_multipart_upload,
    complete_multipart_upload,
    cos_key,
    create_multipart_upload,
    get_presigned_url,
    head_object,
)
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
    upload_urls: list[str] = []
    if storage.type == "cos":
        raw_name = path.basename(payload.filename).strip() or f"{asset.id}.{asset.extension}"
        safe_name = re.sub(r"[\\/]+", "_", raw_name)
        safe_name = re.sub(r"[\s]+", "_", safe_name)
        safe_name = re.sub(r"[^\w.\-()+\[\]_]+", "_", safe_name, flags=re.UNICODE)
        safe_name = safe_name.strip("._-") or f"{asset.id}.{asset.extension}"
        ext = f".{asset.extension}".lower()
        if not safe_name.lower().endswith(ext):
            safe_name = f"{Path(safe_name).stem}{ext}"
        safe_name = safe_name[:120]
        origin_key = cos_key(storage, f"{uuid4().hex[:4]}-{safe_name}")
        asset.origin_key = origin_key
        if multipart:
            cos_upload_id = create_multipart_upload(storage, origin_key)
            db.add(UploadPart(upload=upload, part_number=0, etag=cos_upload_id, size=0))
            upload_urls = [
                get_presigned_url(
                    storage,
                    method="PUT",
                    key=origin_key,
                    params={"partNumber": str(part_number), "uploadId": cos_upload_id},
                    expired=max(settings.cos_signed_url_seconds, 3600),
                )
                for part_number in range(1, total_parts + 1)
            ]
        else:
            upload_urls = [
                get_presigned_url(
                    storage,
                    method="PUT",
                    key=origin_key,
                    expired=max(settings.cos_signed_url_seconds, 3600),
                )
            ]
    db.commit()
    return {
        "upload_id": upload_id,
        "asset_id": asset.id,
        "storage_type": storage.type,
        "multipart": multipart,
        "part_size": settings.part_size,
        "concurrency": 4 if asset_type == "image" else 2,
        "upload_urls": upload_urls,
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
    storage = db.get(Storage, upload.storage_id)
    if storage and storage.type == "cos":
        raise api_error(400, "cos_direct_upload", "COS uploads must use signed URLs")
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
    storage = db.get(Storage, upload.storage_id)
    if storage is None:
        raise api_error(404, "storage_not_found", "Storage not found")
    if storage.type == "cos":
        if not asset.origin_key:
            raise api_error(400, "cos_key_missing", "COS object key is missing")
        upload.status = "uploading"
        asset.status = "uploading"
        if upload.multipart:
            marker = db.scalar(
                select(UploadPart).where(UploadPart.upload_id == upload.id, UploadPart.part_number == 0)
            )
            if marker is None:
                raise api_error(400, "cos_upload_id_missing", "COS UploadId is missing")
            parts = []
            for part in sorted(payload.parts, key=lambda item: item.part_number):
                if not part.etag:
                    raise api_error(400, "etag_missing", "COS multipart ETag is missing")
                parts.append({"PartNumber": part.part_number, "ETag": part.etag})
            if len(parts) < upload.total_parts:
                raise api_error(400, "parts_missing", "Not all parts were uploaded")
            complete_multipart_upload(
                storage,
                key=asset.origin_key,
                upload_id=marker.etag,
                parts=parts,
            )
        else:
            head_object(storage, asset.origin_key)
        upload.uploaded_parts = upload.total_parts
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
    storage = db.get(Storage, upload.storage_id)
    if storage and storage.type == "cos" and upload.asset.origin_key:
        marker = db.scalar(select(UploadPart).where(UploadPart.upload_id == upload.id, UploadPart.part_number == 0))
        if marker is not None:
            abort_multipart_upload(storage, key=upload.asset.origin_key, upload_id=marker.etag)
    upload.status = "canceled"
    upload.asset.status = "failed"
    db.commit()
