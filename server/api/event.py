from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from server.auth.deps import require_admin
from server.core.db import get_db
from server.core.response import ok
from server.model.table import Event, User
from server.schema.type import EventUpdate
from server.service.log import write_log
from server.service.serialize import event_out


router = APIRouter(prefix="/event", tags=["event"])


@router.get("")
def get_event(db: Session = Depends(get_db)):
    event = db.get(Event, 1)
    return ok(event_out(event))


@router.patch("")
def update_event(
    payload: EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    event = db.get(Event, 1)
    for field in ("city", "title", "subtitle", "description", "banner_asset_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(event, field, value)
    write_log(db, actor=user, action="event_update", target_type="event", target_id=1, request=request)
    db.commit()
    return ok(event_out(event))

