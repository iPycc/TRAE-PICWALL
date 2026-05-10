from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(5), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    avatar_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assets: Mapped[list["Asset"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["SessionToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    city: Mapped[str] = mapped_column(String(80), default="Zhuhai")
    title: Mapped[str] = mapped_column(String(160), default="TRAE Friends @ Zhuhai")
    subtitle: Mapped[str] = mapped_column(String(255), default="Build with friends at city")
    description: Mapped[str] = mapped_column(
        Text,
        default="Welcome to TRAE Friends event in Zhuhai! Upload and share your best moments.",
    )
    banner_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_storage_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("storages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Storage(Base):
    __tablename__ = "storages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20), default="local")
    bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    path_prefix: Mapped[str] = mapped_column(String(255), default="")
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    secret_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assets: Mapped[list["Asset"]] = relationship(back_populates="storage")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    storage_id: Mapped[int] = mapped_column(Integer, ForeignKey("storages.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    title: Mapped[str] = mapped_column(String(160))
    original_filename: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(20))
    mime: Mapped[str] = mapped_column(String(100))
    hash: Mapped[str] = mapped_column(String(128), index=True)
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    origin_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumb_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    poster_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="assets")
    storage: Mapped[Storage] = relationship(back_populates="assets")
    uploads: Mapped[list["Upload"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    storage_id: Mapped[int] = mapped_column(Integer, ForeignKey("storages.id"))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    multipart: Mapped[bool] = mapped_column(Boolean, default=False)
    part_size: Mapped[int] = mapped_column(Integer, default=0)
    total_parts: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_parts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    asset: Mapped[Asset] = relationship(back_populates="uploads")
    parts: Mapped[list["UploadPart"]] = relationship(back_populates="upload", cascade="all, delete-orphan")


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (UniqueConstraint("upload_id", "part_number", name="uq_upload_part"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("uploads.id"))
    part_number: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    upload: Mapped[Upload] = relationship(back_populates="parts")


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), index=True)
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor_uid: Mapped[str | None] = mapped_column(String(5), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AssetEvent(Base):
    __tablename__ = "asset_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(20))
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

