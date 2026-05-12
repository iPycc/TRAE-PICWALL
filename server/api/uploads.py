from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.auth.deps import get_current_user
from server.core.db import get_db
from server.core.response import ok
from server.model.table import Asset, User
from server.schema.type import UploadBatchLogIn, UploadCompleteIn, UploadCreateIn
from server.service.log import write_log
from server.service.serialize import asset_out
from server.service.upload import cancel_upload, complete_upload, create_upload, receive_part


router = APIRouter(prefix="/uploads", tags=["uploads"])


def batch_target_id(asset_ids: list[int]) -> str:
    if not asset_ids:
        return "none"
    if len(asset_ids) == 1:
        return str(asset_ids[0])
    return f"{asset_ids[0]}..{asset_ids[-1]} ({len(asset_ids)})"


@router.post("")
def create(
    payload: UploadCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(create_upload(db, payload, user, request))


@router.put("/{upload_id}/parts/{part_number}")
async def put_part(
    upload_id: str,
    part_number: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(await receive_part(db, upload_id, part_number, file, user))


@router.post("/{upload_id}/complete")
def complete(
    upload_id: str,
    payload: UploadCompleteIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = complete_upload(db, upload_id, payload, user, request)
    return ok(asset_out(asset))


@router.delete("/{upload_id}")
def cancel(upload_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cancel_upload(db, upload_id, user)
    return ok({"success": True})


@router.post("/batch-log")
def upload_batch_log(
    payload: UploadBatchLogIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assets = []
    if payload.asset_ids:
        assets = db.scalars(
            select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.user_id == user.id)
        ).all()
    asset_ids = sorted(asset.id for asset in assets)
    image_count = sum(1 for asset in assets if asset.type == "image")
    video_count = sum(1 for asset in assets if asset.type == "video")
    message = (
        f"本次批量上传完成：图片 {image_count} 个，视频 {video_count} 个，"
        f"失败 {payload.failed_count} 个，跳过 {payload.skipped_count} 个。"
    )
    write_log(
        db,
        actor=user,
        action="upload_batch",
        target_type="upload_batch",
        target_id=batch_target_id(asset_ids),
        message=message,
        request=request,
    )
    db.commit()
    return ok(
        {
            "asset_count": len(assets),
            "image_count": image_count,
            "video_count": video_count,
            "failed_count": payload.failed_count,
            "skipped_count": payload.skipped_count,
        }
    )
