from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from server.core.config import get_settings
from server.core.db import Base, engine
from server.model.table import Event, Storage


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    for folder in ("origin", "thumb", "poster", "avatar", "temp"):
        (settings.storage_root / folder).mkdir(parents=True, exist_ok=True)


def ensure_seed(db: Session) -> None:
    settings = get_settings()
    storage = db.scalars(select(Storage).where(Storage.is_active.is_(True), Storage.is_disabled.is_(False))).first()
    if storage is None:
        storage = Storage(
            name="Local Storage",
            type="local",
            path_prefix="",
            local_path=str(Path(settings.storage_root).resolve()),
            is_active=True,
            is_disabled=False,
        )
        db.add(storage)
        db.flush()

    event = db.get(Event, 1)
    if event is None:
        db.add(Event(id=1, active_storage_id=storage.id))
    elif event.active_storage_id is None:
        event.active_storage_id = storage.id
    db.commit()

