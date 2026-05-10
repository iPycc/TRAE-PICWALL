from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from server.auth.deps import get_current_user
from server.core.db import get_db
from server.core.error import api_error
from server.core.response import ok, page as page_response
from server.model.table import Asset, SessionToken, User
from server.schema.type import PasswordUpdate, UserUpdate
from server.service.auth import revoke_user_sessions
from server.service.log import write_log
from server.service.serialize import asset_out, user_out
from server.store.local import save_upload, storage_path
from server.auth.security import hash_password, verify_password
from server.utils.avatar import avatar_colors


router = APIRouter(tags=["users"])


@router.get("/users/me")
def me(user: User = Depends(get_current_user)):
    return ok(user_out(user))


@router.patch("/users/me")
def update_me(
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.email is not None and str(payload.email).lower() != user.email:
        exists = db.scalar(select(User).where(User.email == str(payload.email).lower(), User.id != user.id))
        if exists:
            raise api_error(409, "email_exists", "Email already registered")
        user.email = str(payload.email).lower()
        revoke_user_sessions(db, user.id)
        write_log(db, actor=user, action="email_update", target_type="user", target_id=user.uid, request=request)
    if payload.username is not None:
        user.username = payload.username
    db.commit()
    return ok(user_out(user))


@router.patch("/users/me/password")
def update_password(
    payload: PasswordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise api_error(400, "invalid_password", "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    revoke_user_sessions(db, user.id)
    write_log(db, actor=user, action="password_update", target_type="user", target_id=user.uid, request=request)
    db.commit()
    return ok({"success": True})


@router.put("/users/me/avatar")
async def update_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/") or file.content_type == "image/svg+xml":
        raise api_error(400, "invalid_avatar", "Invalid avatar image")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    key = f"avatar/{user.uid}.{ext}"
    await save_upload(file, key)
    user.avatar_path = key
    user.avatar_mime = file.content_type
    db.commit()
    return ok(user_out(user))


@router.get("/avatars/{uid}")
def avatar(uid: str, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.uid == uid))
    if user is None:
        raise api_error(404, "user_not_found", "User not found")
    if user.avatar_path:
        path = storage_path(user.avatar_path)
        if path.exists():
            return FileResponse(path, media_type=user.avatar_mime)
    initial = (user.username[:1] or "?").upper()
    background, foreground = avatar_colors(user.uid or user.username)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="24" fill="{background}"/><text x="64" y="78" font-family="Arial" font-size="56" font-weight="700" fill="{foreground}" text-anchor="middle">{initial}</text></svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/users/me/assets")
def my_assets(
    page: int = 1,
    page_size: int = 16,
    storage_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Asset).options(joinedload(Asset.user)).where(Asset.user_id == user.id)
    if storage_id:
        stmt = stmt.where(Asset.storage_id == storage_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_number = max(1, page)
    assets = db.scalars(stmt.order_by(Asset.created_at.desc()).offset((page_number - 1) * page_size).limit(page_size)).all()
    return page_response([asset_out(asset) for asset in assets], page_number, page_size, total)


@router.get("/users/me/stats")
def my_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assets = db.scalars(select(Asset).where(Asset.user_id == user.id)).all()
    return ok(
        {
            "asset_count": len(assets),
            "image_count": sum(1 for asset in assets if asset.type == "image"),
            "video_count": sum(1 for asset in assets if asset.type == "video"),
            "view_count": sum(asset.view_count for asset in assets),
            "download_count": sum(asset.download_count for asset in assets),
        }
    )
