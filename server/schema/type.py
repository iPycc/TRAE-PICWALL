from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field

Role = Literal["root", "admin", "user"]
AssetType = Literal["image", "video"]
AssetStatus = Literal["waiting", "uploading", "uploaded", "processing", "ready", "failed"]
StorageType = Literal["cos", "local"]


class UserOut(BaseModel):
    id: int
    uid: str
    username: str
    email: EmailStr
    role: Role
    avatar: str | None = None
    created_at: datetime


class EventOut(BaseModel):
    city: str
    title: str
    subtitle: str
    description: str
    banner_asset_id: int | None = None
    active_storage_id: int | None = None


class StorageOut(BaseModel):
    id: int
    name: str
    type: StorageType
    bucket: str | None = None
    region: str | None = None
    endpoint: str | None = None
    path_prefix: str = ""
    local_path: str | None = None
    secret_configured: bool = False
    is_active: bool
    is_disabled: bool
    created_at: datetime


class AssetOut(BaseModel):
    id: int
    storage_id: int
    user_id: int
    type: AssetType
    status: AssetStatus
    title: str
    original_filename: str
    extension: str
    mime: str
    size: int
    width: int
    height: int
    duration: float | None = None
    url: str
    thumb_url: str | None = None
    poster_url: str | None = None
    is_pinned: bool
    view_count: int
    download_count: int
    created_at: datetime
    owner: UserOut | None = None


class LogOut(BaseModel):
    id: int
    actor_uid: str | None = None
    action: str
    target_type: str
    target_id: str
    message: str
    ip: str | None = None
    created_at: datetime


class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6)
    confirm_password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str


class EventUpdate(BaseModel):
    city: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=160)
    subtitle: str | None = Field(default=None, max_length=255)
    description: str | None = None
    banner_asset_id: int | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None


class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class RoleUpdate(BaseModel):
    role: Role


class AssetUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class PinUpdate(BaseModel):
    pinned: bool


class UploadCreateIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=160)
    size: int = Field(ge=1)
    mime: str = Field(min_length=1, max_length=100)
    type: AssetType


class UploadCompletePart(BaseModel):
    part_number: int
    etag: str | None = None


class UploadCompleteIn(BaseModel):
    parts: list[UploadCompletePart] = []


class UploadBatchLogIn(BaseModel):
    asset_ids: list[int] = []
    failed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)


class StorageCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: StorageType = "local"
    bucket: str | None = None
    region: str | None = None
    endpoint: str | None = None
    path_prefix: str = ""
    local_path: str | None = None
    secret_id: str | None = None
    secret_key: str | None = None


class StorageUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    bucket: str | None = None
    region: str | None = None
    endpoint: str | None = None
    path_prefix: str | None = None
    local_path: str | None = None
    secret_id: str | None = None
    secret_key: str | None = None


class StorageActivationIn(BaseModel):
    active: bool


class StorageThumbnailIn(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1, le=100)
    force: bool = False


class DashboardOut(BaseModel):
    user_count: int
    asset_count: int
    image_count: int
    video_count: int
    view_count: int
    download_count: int


class UserStatsOut(BaseModel):
    asset_count: int
    image_count: int
    video_count: int
    view_count: int
    download_count: int
