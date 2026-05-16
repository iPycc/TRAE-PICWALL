from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from server.auth.deps import get_current_user, get_optional_user, require_admin
from server.core.config import get_settings
from server.core.db import get_db
from server.core.error import api_error
from server.core.response import ok, page as page_response
from server.model.table import User
from server.schema.type import AssetUpdate, PinUpdate
from server.service.asset import (
    assert_public_access,
    delete_asset,
    get_asset,
    list_public_assets,
    pin_asset,
    record_asset_event,
    update_asset_title,
)
from server.service.serialize import asset_out
from server.store.local import storage_path
from server.store.cos import object_download_url, object_thumbnail_url
from server.task.media import ensure_thumbnail


router = APIRouter(prefix="/assets", tags=["assets"])


def with_web_base(path: str) -> str:
    if not path.startswith("/"):
        return path
    base = (get_settings().web_base_path or "").rstrip("/")
    if not base:
        return path
    if path.startswith(base + "/") or path == base:
        return path
    return f"{base}{path}"


@router.get("")
def list_assets(
    page: int = 1,
    page_size: int = 16,
    type: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    page_number = max(1, page)
    page_size = min(page_size, 100)
    assets, total = list_public_assets(
        db,
        page_number=page_number,
        page_size=page_size,
        asset_type=type,
        q=q,
    )
    return page_response([asset_out(asset) for asset in assets], page_number, page_size, total)


@router.get("/{asset_id}")
def get_asset_detail(asset_id: int, db: Session = Depends(get_db)):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    return ok(asset_out(asset))


@router.get("/{asset_id}/preview")
def preview_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    record_asset_event(db, asset=asset, event_name="view", user=user, request=request)
    db.commit()
    if asset.storage and asset.storage.type == "cos":
        if not asset.origin_key:
            raise api_error(404, "file_not_found", "File not found")
        return ok({"url": object_download_url(asset.storage, asset.origin_key), "asset": asset_out(asset)})
    return ok({"url": f"/api/v1/assets/{asset.id}/file", "asset": asset_out(asset)})


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    record_asset_event(db, asset=asset, event_name="download", user=user, request=request)
    db.commit()
    if asset.storage and asset.storage.type == "cos":
        if not asset.origin_key:
            raise api_error(404, "file_not_found", "File not found")
        return ok(
            {
                "url": object_download_url(
                    asset.storage,
                    asset.origin_key,
                    filename=asset.original_filename,
                ),
                "asset": asset_out(asset),
            }
        )
    return ok({"url": with_web_base(f"/api/v1/assets/{asset.id}/file"), "asset": asset_out(asset)})


@router.get("/{asset_id}/file")
def asset_file(asset_id: int, download: int = 0, db: Session = Depends(get_db)):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    if not asset.origin_key:
        raise api_error(404, "file_not_found", "File not found")
    if asset.storage and asset.storage.type == "cos":
        return RedirectResponse(
            object_download_url(
                asset.storage,
                asset.origin_key,
                filename=asset.original_filename if download else None,
            )
        )
    path = storage_path(asset.origin_key)
    if not path.exists():
        raise api_error(404, "file_not_found", "File not found")
    return FileResponse(
        path,
        media_type=asset.mime,
        filename=asset.original_filename if download else None,
    )


@router.get("/{asset_id}/thumb")
def asset_thumb(asset_id: int, db: Session = Depends(get_db)):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    if asset.type != "image":
        raise api_error(404, "thumb_not_found", "Thumbnail not found")
    if asset.storage and asset.storage.type == "cos":
        if not asset.origin_key:
            raise api_error(404, "file_not_found", "File not found")
        return RedirectResponse(object_thumbnail_url(asset.storage, asset.origin_key))
    try:
        path = ensure_thumbnail(asset)
        db.commit()
    except FileNotFoundError:
        raise api_error(404, "file_not_found", "File not found")
    return FileResponse(path, media_type="image/webp")


@router.get("/{asset_id}/poster")
def asset_poster(asset_id: int, db: Session = Depends(get_db)):
    asset = get_asset(db, asset_id)
    assert_public_access(asset)
    if not asset.poster_key:
        raise api_error(404, "file_not_found", "File not found")
    if asset.storage and asset.storage.type == "cos":
        return RedirectResponse(object_download_url(asset.storage, asset.poster_key))
    path = storage_path(asset.poster_key)
    if not path.exists():
        raise api_error(404, "file_not_found", "File not found")
    return FileResponse(path)


@router.patch("/{asset_id}")
def patch_asset(
    asset_id: int,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = get_asset(db, asset_id)
    update_asset_title(user, asset, payload.title)
    db.commit()
    return ok(asset_out(asset))


@router.delete("/{asset_id}")
def remove_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = get_asset(db, asset_id)
    delete_asset(db, user, asset, request)
    db.commit()
    return ok({"success": True})


@router.patch("/{asset_id}/pin")
def patch_pin(
    asset_id: int,
    payload: PinUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    asset = get_asset(db, asset_id)
    pin_asset(user, asset, payload.pinned, db, request)
    db.commit()
    return ok(asset_out(asset))
