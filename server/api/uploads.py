from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session
from server.auth.deps import get_current_user
from server.core.db import get_db
from server.core.response import ok
from server.model.table import User
from server.schema.type import UploadCheckIn, UploadCompleteIn, UploadCreateIn
from server.service.serialize import asset_out
from server.service.upload import cancel_upload, check_instant, complete_upload, create_upload, receive_part


router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/checks")
def checks(
    payload: UploadCheckIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = check_instant(db, payload, user, request)
    data = {"instant": result["instant"]}
    if result.get("asset"):
        data["asset"] = asset_out(result["asset"])
    return ok(data)


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

