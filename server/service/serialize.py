from server.core.config import get_settings
from server.model.table import Asset, Event, Log, Storage, User


settings = get_settings()


def public_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://") or path.startswith("/"):
        return path
    return f"/{path.lstrip('/')}"


def user_out(user: User) -> dict:
    avatar_version = int(user.updated_at.timestamp()) if user.updated_at else 0
    return {
        "id": user.id,
        "uid": user.uid,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "avatar": f"/api/v1/avatars/{user.uid}?v={avatar_version}",
        "created_at": user.created_at,
    }


def event_out(event: Event) -> dict:
    return {
        "city": event.city,
        "title": event.title,
        "subtitle": event.subtitle,
        "description": event.description,
        "banner_asset_id": event.banner_asset_id,
        "active_storage_id": event.active_storage_id,
    }


def storage_out(storage: Storage) -> dict:
    return {
        "id": storage.id,
        "name": storage.name,
        "type": storage.type,
        "bucket": storage.bucket,
        "region": storage.region,
        "endpoint": storage.endpoint,
        "path_prefix": storage.path_prefix,
        "local_path": storage.local_path,
        "is_active": storage.is_active,
        "is_disabled": storage.is_disabled,
        "created_at": storage.created_at,
    }


def asset_out(asset: Asset, include_owner: bool = True) -> dict:
    url = f"/api/v1/assets/{asset.id}/file"
    thumb_url = f"/api/v1/assets/{asset.id}/thumb" if asset.thumb_key else url
    poster_url = f"/api/v1/assets/{asset.id}/poster" if asset.poster_key else None
    return {
        "id": asset.id,
        "storage_id": asset.storage_id,
        "user_id": asset.user_id,
        "type": asset.type,
        "status": asset.status,
        "title": asset.title,
        "original_filename": asset.original_filename,
        "extension": asset.extension,
        "mime": asset.mime,
        "size": asset.size,
        "width": asset.width,
        "height": asset.height,
        "duration": float(asset.duration) if asset.duration is not None else None,
        "url": url,
        "thumb_url": thumb_url,
        "poster_url": poster_url,
        "is_pinned": asset.is_pinned,
        "view_count": asset.view_count,
        "download_count": asset.download_count,
        "created_at": asset.created_at,
        "owner": user_out(asset.user) if include_owner and asset.user else None,
    }


def log_out(log: Log) -> dict:
    return {
        "id": log.id,
        "actor_uid": log.actor_uid,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "message": log.message,
        "created_at": log.created_at,
    }
