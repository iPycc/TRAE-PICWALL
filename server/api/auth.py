from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from server.auth.deps import bearer, get_current_user
from server.core.db import get_db
from server.core.response import ok
from server.model.table import User
from server.schema.type import LoginIn, RefreshIn, RegisterIn
from server.service import auth as auth_service
from server.service.serialize import user_out


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    return ok(auth_service.register(db, payload, request))


@router.post("/sessions")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    return ok(auth_service.login(db, payload, request))


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ok(user_out(user))


@router.post("/tokens/refresh")
def refresh(payload: RefreshIn, request: Request, db: Session = Depends(get_db)):
    return ok(auth_service.refresh(db, payload.refresh_token, request))


@router.delete("/sessions/current")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if credentials:
        auth_service.logout_current(db, credentials.credentials)
    return ok({"success": True})

