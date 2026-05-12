from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from server.auth.deps import require_admin
from server.core.db import get_db
from server.core.error import api_error
from server.core.response import ok, page as page_response
from server.model.table import Asset, Log, Storage, User
from server.schema.type import RoleUpdate, StorageActivationIn, StorageCreateIn, StorageUpdateIn
from server.service.asset import delete_asset
from server.service.log import write_log
from server.service.serialize import asset_out, log_out, storage_out, user_out
from server.service.storage import activate_storage, create_storage, update_storage


router = APIRouter(prefix="/admin", tags=["admin"])


def can_operate_user(actor: User, target: User, role_change: bool = False) -> None:
    if actor.id == target.id:
        raise api_error(403, "forbidden", "Cannot operate yourself")
    if target.role == "root":
        raise api_error(403, "forbidden", "Cannot operate root")
    if actor.role == "admin" and target.role == "admin":
        raise api_error(403, "forbidden", "Admin cannot operate other admin")
    if role_change and actor.role == "admin" and target.role != "user":
        raise api_error(403, "forbidden", "Admin can only promote user")


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    assets = db.scalars(select(Asset)).all()
    return ok(
        {
            "user_count": db.scalar(select(func.count(User.id))) or 0,
            "asset_count": len(assets),
            "image_count": sum(1 for asset in assets if asset.type == "image"),
            "video_count": sum(1 for asset in assets if asset.type == "video"),
            "view_count": sum(asset.view_count for asset in assets),
            "download_count": sum(asset.download_count for asset in assets),
        }
    )


@router.get("/users")
def users(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(User).order_by(User.created_at.asc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_number = max(1, page)
    users_list = db.scalars(stmt.offset((page_number - 1) * page_size).limit(page_size)).all()
    return page_response([user_out(user) for user in users_list], page_number, page_size, total)


@router.get("/users/{uid}")
def user_detail(uid: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.scalar(select(User).where(User.uid == uid))
    if user is None:
        raise api_error(404, "user_not_found", "User not found")
    return ok(user_out(user))


@router.get("/users/{uid}/assets")
def user_assets(uid: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.scalar(select(User).where(User.uid == uid))
    if user is None:
        raise api_error(404, "user_not_found", "User not found")
    assets = db.scalars(select(Asset).options(joinedload(Asset.user)).where(Asset.user_id == user.id)).all()
    return page_response([asset_out(asset) for asset in assets], 1, len(assets) or 16, len(assets))


@router.patch("/users/{uid}/role")
def update_role(
    uid: str,
    payload: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    target = db.scalar(select(User).where(User.uid == uid))
    if target is None:
        raise api_error(404, "user_not_found", "User not found")
    can_operate_user(actor, target, role_change=True)
    if target.role == "admin" and payload.role == "user" and actor.role != "root":
        raise api_error(403, "forbidden", "Only root can demote admin")
    if payload.role == "root":
        raise api_error(403, "forbidden", "Root role is unique")
    target.role = payload.role
    write_log(db, actor=actor, action="role_change", target_type="user", target_id=target.uid, request=request)
    db.commit()
    return ok(user_out(target))


@router.delete("/users/{uid}")
def delete_user(
    uid: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    target = db.scalar(select(User).where(User.uid == uid))
    if target is None:
        raise api_error(404, "user_not_found", "User not found")
    can_operate_user(actor, target)
    write_log(db, actor=actor, action="delete_user", target_type="user", target_id=target.uid, request=request)
    db.delete(target)
    db.commit()
    return ok({"success": True})


@router.get("/assets")
def assets(
    page: int = 1,
    page_size: int = 50,
    storage_id: int | None = None,
    owner_uid: str | None = None,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(Asset).options(joinedload(Asset.user))
    if storage_id:
        stmt = stmt.where(Asset.storage_id == storage_id)
    if owner_uid:
        owner = db.scalar(select(User).where(User.uid == owner_uid))
        if owner:
            stmt = stmt.where(Asset.user_id == owner.id)
    if type:
        stmt = stmt.where(Asset.type == type)
    if status:
        stmt = stmt.where(Asset.status == status)
    if q:
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(
            Asset.title.ilike(keyword) | Asset.original_filename.ilike(keyword)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_number = max(1, page)
    rows = db.scalars(stmt.order_by(Asset.created_at.desc()).offset((page_number - 1) * page_size).limit(page_size)).all()
    return page_response([asset_out(asset) for asset in rows], page_number, page_size, total)


@router.get("/storages")
def storages(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(Storage).order_by(Storage.created_at.asc())).all()
    return page_response([storage_out(storage) for storage in rows], 1, len(rows) or 16, len(rows))


@router.post("/storages")
def add_storage(
    payload: StorageCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    storage = create_storage(db, payload)
    write_log(db, actor=actor, action="storage_create", target_type="storage", target_id=storage.id, request=request)
    db.commit()
    return ok(storage_out(storage))


@router.get("/storages/{storage_id}")
def storage_detail(storage_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    storage = db.get(Storage, storage_id)
    if storage is None:
        raise api_error(404, "storage_not_found", "Storage not found")
    return ok(storage_out(storage))


@router.patch("/storages/{storage_id}")
def patch_storage(
    storage_id: int,
    payload: StorageUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    storage = db.get(Storage, storage_id)
    if storage is None:
        raise api_error(404, "storage_not_found", "Storage not found")
    update_storage(storage, payload)
    db.commit()
    return ok(storage_out(storage))


@router.patch("/storages/{storage_id}/activation")
def storage_activation(
    storage_id: int,
    payload: StorageActivationIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    storage = db.get(Storage, storage_id)
    if storage is None:
        raise api_error(404, "storage_not_found", "Storage not found")
    if payload.active:
        activate_storage(db, storage)
        write_log(db, actor=actor, action="storage_switch", target_type="storage", target_id=storage.id, request=request)
    db.commit()
    return ok(storage_out(storage))


@router.delete("/storages/{storage_id}")
def disable_storage(
    storage_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    storage = db.get(Storage, storage_id)
    if storage is None:
        raise api_error(404, "storage_not_found", "Storage not found")
    if storage.is_active:
        raise api_error(400, "storage_active", "Active storage cannot be disabled")
    storage.is_disabled = True
    write_log(db, actor=actor, action="storage_disable", target_type="storage", target_id=storage.id, request=request)
    db.commit()
    return ok(storage_out(storage))


@router.get("/logs")
def logs(
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
    actor_uid: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(Log)
    if action:
        stmt = stmt.where(Log.action == action)
    if actor_uid:
        stmt = stmt.where(Log.actor_uid == actor_uid)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_number = max(1, page)
    rows = db.scalars(stmt.order_by(Log.created_at.desc()).offset((page_number - 1) * page_size).limit(page_size)).all()
    return page_response([log_out(log) for log in rows], page_number, page_size, total)
