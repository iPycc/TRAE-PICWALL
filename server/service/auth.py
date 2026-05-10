from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from jwt import InvalidTokenError
from server.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_hash,
    verify_password,
)
from server.core.config import get_settings
from server.core.error import api_error
from server.model.table import SessionToken, User
from server.schema.type import LoginIn, RegisterIn
from server.service.log import write_log
from server.service.serialize import user_out


def as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def next_uid(db: Session, role: str) -> str:
    prefix = {"root": "R", "admin": "A", "user": "U"}[role]
    count = db.scalar(select(func.count(User.id))) or 0
    for number in range(count + 1, count + 10000):
        uid = f"{prefix}{number:04d}"[-5:]
        if db.scalar(select(User).where(User.uid == uid)) is None:
            return uid
    return f"{prefix}{uuid4().hex[:4].upper()}"


def make_session(db: Session, user: User, request: Request | None = None) -> dict:
    settings = get_settings()
    session_id = f"sess_{uuid4().hex}"
    refresh_token = create_refresh_token(user.id, session_id)
    db.add(
        SessionToken(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=token_hash(refresh_token),
            ip=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        )
    )
    access_token = create_access_token(user.id, session_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_out(user),
    }


def register(db: Session, payload: RegisterIn, request: Request) -> dict:
    if payload.password != payload.confirm_password:
        raise api_error(400, "password_mismatch", "Passwords do not match")
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise api_error(409, "email_exists", "Email already registered")
    user_count = db.scalar(select(func.count(User.id))) or 0
    role = "root" if user_count == 0 else "user"
    user = User(
        uid=next_uid(db, role),
        username=payload.username,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=role,
        last_ip=request.client.host if request.client else None,
    )
    db.add(user)
    db.flush()
    write_log(db, actor=user, action="register", target_type="user", target_id=user.uid, request=request)
    tokens = make_session(db, user, request)
    write_log(db, actor=user, action="login", target_type="user", target_id=user.uid, request=request)
    db.commit()
    return tokens


def login(db: Session, payload: LoginIn, request: Request) -> dict:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise api_error(401, "invalid_credentials", "Invalid email or password")
    user.last_ip = request.client.host if request.client else None
    tokens = make_session(db, user, request)
    write_log(db, actor=user, action="login", target_type="user", target_id=user.uid, request=request)
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str, request: Request) -> dict:
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError:
        raise api_error(401, "invalid_token", "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise api_error(401, "invalid_token", "Invalid refresh token")
    session = db.get(SessionToken, payload.get("sid"))
    if session is None or session.refresh_token_hash != token_hash(refresh_token):
        raise api_error(401, "session_not_found", "Session not found")
    if as_aware(session.expires_at) < datetime.now(timezone.utc):
        raise api_error(401, "session_expired", "Session expired")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise api_error(401, "user_not_found", "User not found")
    db.delete(session)
    tokens = make_session(db, user, request)
    db.commit()
    return tokens


def logout_current(db: Session, token: str) -> None:
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        return
    session_id = payload.get("sid")
    if session_id:
        session = db.get(SessionToken, session_id)
        if session:
            db.delete(session)
            db.commit()


def revoke_user_sessions(db: Session, user_id: int) -> None:
    for session in db.scalars(select(SessionToken).where(SessionToken.user_id == user_id)).all():
        db.delete(session)
