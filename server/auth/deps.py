from datetime import datetime, timezone
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session
from server.auth.security import decode_token
from server.core.db import get_db
from server.core.error import api_error
from server.model.table import SessionToken, User


bearer = HTTPBearer(auto_error=False)


def as_aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.now(timezone.utc).tzinfo)
    return value


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise api_error(401, "not_authenticated", "Authentication required")
    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError:
        raise api_error(401, "invalid_token", "Invalid token")
    if payload.get("type") != "access":
        raise api_error(401, "invalid_token", "Invalid access token")
    session_id = payload.get("sid")
    user_id = payload.get("sub")
    if not session_id or not user_id:
        raise api_error(401, "invalid_token", "Invalid token payload")
    session = db.get(SessionToken, session_id)
    if session is None or as_aware(session.expires_at) < datetime.now(timezone.utc):
        raise api_error(401, "session_expired", "Session expired")
    user = db.get(User, int(user_id))
    if user is None:
        raise api_error(401, "user_not_found", "User not found")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except Exception:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("root", "admin"):
        raise api_error(403, "forbidden", "Admin permission required")
    return user
