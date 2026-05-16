from sqlalchemy import func, select
from sqlalchemy.orm import Session
from server.core.config import get_settings
from server.core.crypto import encrypt_secret
from server.core.error import api_error
from server.model.table import Asset, Event, Storage
from server.schema.type import StorageCreateIn, StorageThumbnailIn, StorageUpdateIn
from server.store.cos import (
    clean_prefix,
    generate_image_thumbnail,
    list_objects,
    put_bucket_cors,
    validate_bucket_access,
)


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_prefix(value: str | None) -> str:
    return clean_prefix(value)


def _require_cos_payload(payload: StorageCreateIn) -> None:
    if not _blank_to_none(payload.bucket):
        raise api_error(400, "cos_bucket_required", "COS bucket is required")
    if not _blank_to_none(payload.region):
        raise api_error(400, "cos_region_required", "COS region is required")
    if not _blank_to_none(payload.secret_id) or not _blank_to_none(payload.secret_key):
        raise api_error(400, "cos_secret_required", "COS SecretId and SecretKey are required")


def active_storage(db: Session) -> Storage:
    event = db.get(Event, 1)
    storage = db.get(Storage, event.active_storage_id) if event and event.active_storage_id else None
    if storage is None:
        storage = db.scalars(select(Storage).where(Storage.is_active.is_(True), Storage.is_disabled.is_(False))).first()
    if storage is None or storage.is_disabled:
        raise api_error(500, "active_storage_missing", "Active storage is missing")
    return storage


def create_storage(db: Session, payload: StorageCreateIn) -> Storage:
    if payload.type == "local":
        local_path = payload.local_path or str(get_settings().storage_root.resolve())
    else:
        _require_cos_payload(payload)
        local_path = payload.local_path
    storage = Storage(
        name=payload.name,
        type=payload.type,
        bucket=_blank_to_none(payload.bucket),
        region=_blank_to_none(payload.region),
        endpoint=_blank_to_none(payload.endpoint),
        path_prefix=_normalize_prefix(payload.path_prefix),
        local_path=local_path,
        secret_id_encrypted=encrypt_secret(_blank_to_none(payload.secret_id)),
        secret_key_encrypted=encrypt_secret(_blank_to_none(payload.secret_key)),
        is_active=False,
        is_disabled=False,
    )
    db.add(storage)
    db.flush()
    return storage


def update_storage(storage: Storage, payload: StorageUpdateIn) -> Storage:
    for field in ("name", "bucket", "region", "endpoint", "local_path"):
        value = getattr(payload, field)
        if value is not None:
            setattr(storage, field, _blank_to_none(value))
    if payload.path_prefix is not None:
        storage.path_prefix = _normalize_prefix(payload.path_prefix)
    if _blank_to_none(payload.secret_id) is not None:
        storage.secret_id_encrypted = encrypt_secret(_blank_to_none(payload.secret_id))
    if _blank_to_none(payload.secret_key) is not None:
        storage.secret_key_encrypted = encrypt_secret(_blank_to_none(payload.secret_key))
    return storage


def activate_storage(db: Session, storage: Storage) -> None:
    if storage.is_disabled:
        raise api_error(400, "storage_disabled", "Disabled storage cannot be activated")
    for item in db.scalars(select(Storage)).all():
        item.is_active = item.id == storage.id
    event = db.get(Event, 1)
    if event:
        event.active_storage_id = storage.id


def cors_origins(request_origin: str | None = None) -> list[str]:
    settings = get_settings()
    origins = list(dict.fromkeys(settings.cos_cors_origin_list))
    if request_origin and request_origin not in origins:
        origins.append(request_origin)
    return origins or ["*"]


def configure_storage_cors(storage: Storage, request_origin: str | None = None) -> None:
    if storage.type != "cos":
        return
    validate_bucket_access(storage)
    put_bucket_cors(storage, cors_origins(request_origin))


def cos_storage_objects(storage: Storage, *, prefix: str = "", marker: str = "", max_keys: int = 100) -> dict:
    if storage.type != "cos":
        raise api_error(400, "storage_not_cos", "Storage is not a COS bucket")
    return list_objects(storage, prefix=prefix, marker=marker, max_keys=max_keys)


def generate_storage_thumbnails(db: Session, storage: Storage, payload: StorageThumbnailIn) -> dict:
    if storage.type != "cos":
        raise api_error(400, "storage_not_cos", "Storage is not a COS bucket")
    stmt = select(Asset).where(
        Asset.storage_id == storage.id,
        Asset.type == "image",
        Asset.status == "ready",
    )
    if not payload.force:
        stmt = stmt.where(Asset.thumb_key.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Asset.created_at.asc())
        .offset((payload.page - 1) * payload.page_size)
        .limit(payload.page_size)
    ).all()

    processed = 0
    skipped = 0
    failed: list[dict[str, str | int]] = []
    for asset in rows:
        if asset.thumb_key and not payload.force:
            skipped += 1
            continue
        try:
            generate_image_thumbnail(storage, asset, force=payload.force)
            processed += 1
        except Exception as exc:
            failed.append({"asset_id": asset.id, "message": str(exc)})

    db.flush()
    remaining = max(total - processed - skipped - len(failed), 0)
    has_more = payload.page * payload.page_size < total if payload.force else remaining > 0 and (processed + skipped) > 0
    next_page = payload.page + 1 if payload.force else 1
    return {
        "storage_id": storage.id,
        "page": payload.page,
        "page_size": payload.page_size,
        "total": total,
        "processed": processed,
        "skipped": skipped,
        "failed_count": len(failed),
        "failed": failed,
        "remaining": remaining,
        "has_more": has_more,
        "next_page": next_page if has_more else None,
    }
