from pathlib import Path
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from server.core.error import api_error
from server.model.table import Asset, AssetEvent, Event, User
from server.service.log import write_log
from server.service.storage import active_storage
from server.store.local import remove_key


def list_public_assets(db: Session, *, page_number: int, page_size: int, asset_type: str | None) -> tuple[list[Asset], int]:
    storage = active_storage(db)
    stmt = (
        select(Asset)
        .options(joinedload(Asset.user))
        .where(Asset.storage_id == storage.id, Asset.status == "ready")
    )
    if asset_type:
        stmt = stmt.where(Asset.type == asset_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    assets = db.scalars(
        stmt.order_by(Asset.is_pinned.desc(), Asset.created_at.desc())
        .offset((page_number - 1) * page_size)
        .limit(page_size)
    ).all()
    return assets, total


def get_asset(db: Session, asset_id: int) -> Asset:
    asset = db.scalar(select(Asset).options(joinedload(Asset.user), joinedload(Asset.storage)).where(Asset.id == asset_id))
    if asset is None:
        raise api_error(404, "asset_not_found", "Asset not found")
    return asset


def assert_public_access(asset: Asset) -> None:
    event = asset.storage.is_active if asset.storage else False
    if asset.status != "ready" or not event or (asset.storage and asset.storage.is_disabled):
        raise api_error(404, "asset_not_found", "Asset not found")


def record_asset_event(
    db: Session,
    *,
    asset: Asset,
    event_name: str,
    user: User | None,
    request: Request,
) -> None:
    if event_name == "view":
        asset.view_count += 1
    elif event_name == "download":
        asset.download_count += 1
    db.add(
        AssetEvent(
            asset_id=asset.id,
            user_id=user.id if user else None,
            event=event_name,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


def can_delete_asset(actor: User, asset: Asset) -> bool:
    owner = asset.user
    if actor.role == "root":
        return True
    if actor.id == asset.user_id:
        return True
    if actor.role == "admin" and owner and owner.role == "user":
        return True
    return False


def delete_asset(db: Session, actor: User, asset: Asset, request: Request) -> None:
    if not can_delete_asset(actor, asset):
        raise api_error(403, "forbidden", "Cannot delete this asset")
    write_log(db, actor=actor, action="delete", target_type="asset", target_id=asset.id, request=request)
    remove_key(asset.origin_key)
    remove_key(asset.thumb_key)
    remove_key(asset.poster_key)
    db.delete(asset)


def update_asset_title(actor: User, asset: Asset, title: str) -> None:
    if actor.id != asset.user_id:
        raise api_error(403, "forbidden", "Only asset owner can update title")
    asset.title = keep_extension(title, asset.extension)


def keep_extension(title: str, extension: str) -> str:
    ext = f".{extension.lower().lstrip('.')}"
    if title.lower().endswith(ext):
        return title
    stem = Path(title).stem if Path(title).suffix else title
    return f"{stem}{ext}"


def pin_asset(actor: User, asset: Asset, pinned: bool, db: Session, request: Request) -> None:
    if actor.role not in ("root", "admin"):
        raise api_error(403, "forbidden", "Admin permission required")
    asset.is_pinned = pinned
    write_log(db, actor=actor, action="pin", target_type="asset", target_id=asset.id, request=request)

