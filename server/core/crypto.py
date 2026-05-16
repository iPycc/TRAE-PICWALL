import base64
import hashlib

from server.core.config import get_settings
from server.core.error import api_error

try:
    from cryptography.fernet import Fernet, InvalidToken
except ModuleNotFoundError:  # pragma: no cover - dependency is declared in requirements
    Fernet = None
    InvalidToken = Exception


PREFIX = "fernet:"


def _fernet():
    if Fernet is None:
        raise api_error(
            500,
            "crypto_dependency_missing",
            "cryptography is required to encrypt storage secrets",
        )
    settings = get_settings()
    secret = settings.storage_secret_key or settings.jwt_secret
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(PREFIX):
        return value
    token = value[len(PREFIX) :].encode("utf-8")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise api_error(500, "secret_decrypt_failed", "Storage secret cannot be decrypted") from exc
