from fastapi import Request
from sqlalchemy.orm import Session
from server.model.table import Log, User


def write_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | int,
    message: str = "",
    request: Request | None = None,
) -> None:
    db.add(
        Log(
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else "guest",
            actor_uid=actor.uid if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            message=message,
            ip=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
    )

