from sqlalchemy import select
from sqlalchemy.orm import Session
from server.core.config import get_settings
from server.core.error import api_error
from server.model.table import Event, Storage
from server.schema.type import StorageCreateIn, StorageUpdateIn


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
        local_path = payload.local_path
    storage = Storage(
        name=payload.name,
        type=payload.type,
        bucket=payload.bucket,
        region=payload.region,
        endpoint=payload.endpoint,
        path_prefix=payload.path_prefix,
        local_path=local_path,
        secret_id_encrypted=payload.secret_id,
        secret_key_encrypted=payload.secret_key,
        is_active=False,
        is_disabled=False,
    )
    db.add(storage)
    db.flush()
    return storage


def update_storage(storage: Storage, payload: StorageUpdateIn) -> Storage:
    for field in ("name", "bucket", "region", "endpoint", "path_prefix", "local_path"):
        value = getattr(payload, field)
        if value is not None:
            setattr(storage, field, value)
    if payload.secret_id is not None:
        storage.secret_id_encrypted = payload.secret_id
    if payload.secret_key is not None:
        storage.secret_key_encrypted = payload.secret_key
    return storage


def activate_storage(db: Session, storage: Storage) -> None:
    if storage.is_disabled:
        raise api_error(400, "storage_disabled", "Disabled storage cannot be activated")
    for item in db.scalars(select(Storage)).all():
        item.is_active = item.id == storage.id
    event = db.get(Event, 1)
    if event:
        event.active_storage_id = storage.id

