import json
from urllib.parse import quote

from server.core.config import get_settings
from server.core.crypto import decrypt_secret
from server.core.error import api_error
from server.model.table import Asset, Storage


def _sdk():
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ModuleNotFoundError as exc:
        raise api_error(
            500,
            "cos_sdk_missing",
            "cos-python-sdk-v5 is required for COS storage",
        ) from exc
    return CosConfig, CosS3Client


def clean_prefix(prefix: str | None) -> str:
    return (prefix or "").replace("\\", "/").strip("/")


def cos_key(storage: Storage, key: str) -> str:
    safe_key = key.replace("\\", "/").lstrip("/")
    prefix = clean_prefix(storage.path_prefix)
    return f"{prefix}/{safe_key}" if prefix else safe_key


def assert_cos_storage(storage: Storage) -> None:
    if storage.type != "cos":
        raise api_error(400, "storage_not_cos", "Storage is not a COS bucket")
    if not storage.bucket or not storage.region:
        raise api_error(400, "cos_config_incomplete", "COS bucket and region are required")
    if not storage.secret_id_encrypted or not storage.secret_key_encrypted:
        raise api_error(400, "cos_secret_missing", "COS SecretId and SecretKey are required")


def client_for(storage: Storage):
    assert_cos_storage(storage)
    secret_id = decrypt_secret(storage.secret_id_encrypted)
    secret_key = decrypt_secret(storage.secret_key_encrypted)
    if not secret_id or not secret_key:
        raise api_error(400, "cos_secret_missing", "COS SecretId and SecretKey are required")
    CosConfig, CosS3Client = _sdk()
    config = CosConfig(
        Region=storage.region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Scheme="https",
    )
    return CosS3Client(config)


def validate_bucket_access(storage: Storage) -> None:
    try:
        client_for(storage).head_bucket(Bucket=storage.bucket)
    except Exception as exc:
        raise api_error(400, "cos_bucket_unavailable", f"COS bucket is unavailable: {exc}") from exc


def put_bucket_cors(storage: Storage, origins: list[str]) -> None:
    cors_origins = origins or ["*"]
    try:
        client_for(storage).put_bucket_cors(
            Bucket=storage.bucket,
            CORSConfiguration={
                "CORSRule": [
                    {
                        "ID": "picwall-direct-upload",
                        "MaxAgeSeconds": 3600,
                        "AllowedOrigin": cors_origins,
                        "AllowedMethod": ["GET", "HEAD", "PUT", "POST", "DELETE"],
                        "AllowedHeader": ["*"],
                        "ExposeHeader": [
                            "ETag",
                            "Content-Length",
                            "Content-Type",
                            "x-cos-request-id",
                        ],
                    }
                ]
            },
        )
    except Exception as exc:
        raise api_error(400, "cos_cors_failed", f"Failed to configure COS CORS: {exc}") from exc


def get_presigned_url(
    storage: Storage,
    *,
    method: str,
    key: str,
    params: dict[str, str] | None = None,
    expired: int | None = None,
) -> str:
    settings = get_settings()
    try:
        return client_for(storage).get_presigned_url(
            Method=method,
            Bucket=storage.bucket,
            Key=key,
            Params=params or {},
            Expired=expired or settings.cos_signed_url_seconds,
        )
    except Exception as exc:
        raise api_error(400, "cos_sign_failed", f"Failed to sign COS URL: {exc}") from exc


def object_download_url(storage: Storage, key: str, *, filename: str | None = None) -> str:
    params = None
    if filename:
        quoted = quote(filename)
        params = {
            "response-content-disposition": (
                f"attachment; filename*=UTF-8''{quoted}"
            )
        }
    return get_presigned_url(storage, method="GET", key=key, params=params)


def object_thumbnail_url(
    storage: Storage,
    key: str,
    *,
    max_size: int = 480,
    quality: int = 80,
) -> str:
    operation = f"imageMogr2/auto-orient/thumbnail/{max_size}x{max_size}>/strip/format/webp/quality/{quality}"
    return get_presigned_url(storage, method="GET", key=key, params={operation: ""})


def create_multipart_upload(storage: Storage, key: str) -> str:
    try:
        response = client_for(storage).create_multipart_upload(Bucket=storage.bucket, Key=key)
        upload_id = response.get("UploadId")
    except Exception as exc:
        raise api_error(400, "cos_multipart_failed", f"Failed to create COS multipart upload: {exc}") from exc
    if not upload_id:
        raise api_error(400, "cos_multipart_failed", "COS did not return UploadId")
    return upload_id


def complete_multipart_upload(
    storage: Storage,
    *,
    key: str,
    upload_id: str,
    parts: list[dict[str, str | int]],
) -> None:
    try:
        client_for(storage).complete_multipart_upload(
            Bucket=storage.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Part": parts},
        )
    except Exception as exc:
        raise api_error(400, "cos_complete_failed", f"Failed to complete COS multipart upload: {exc}") from exc


def abort_multipart_upload(storage: Storage, *, key: str, upload_id: str) -> None:
    try:
        client_for(storage).abort_multipart_upload(
            Bucket=storage.bucket,
            Key=key,
            UploadId=upload_id,
        )
    except Exception:
        return


def head_object(storage: Storage, key: str) -> dict:
    try:
        return client_for(storage).head_object(Bucket=storage.bucket, Key=key)
    except Exception as exc:
        raise api_error(404, "cos_object_missing", f"COS object is missing: {exc}") from exc


def delete_keys(storage: Storage, keys: list[str | None]) -> None:
    clean_keys = [key for key in keys if key]
    if not clean_keys:
        return
    client = client_for(storage)
    try:
        if len(clean_keys) == 1:
            client.delete_object(Bucket=storage.bucket, Key=clean_keys[0])
            return
        client.delete_objects(
            Bucket=storage.bucket,
            Delete={"Object": [{"Key": key} for key in clean_keys]},
        )
    except Exception as exc:
        raise api_error(400, "cos_delete_failed", f"Failed to delete COS object: {exc}") from exc


def list_objects(
    storage: Storage,
    *,
    prefix: str = "",
    marker: str = "",
    max_keys: int = 100,
) -> dict:
    try:
        return client_for(storage).list_objects(
            Bucket=storage.bucket,
            Prefix=cos_key(storage, prefix) if prefix else clean_prefix(storage.path_prefix),
            Marker=marker,
            MaxKeys=max(1, min(max_keys, 1000)),
        )
    except Exception as exc:
        raise api_error(400, "cos_list_failed", f"Failed to list COS objects: {exc}") from exc


def generate_image_thumbnail(
    storage: Storage,
    asset: Asset,
    *,
    force: bool = False,
    max_size: int = 360,
    quality: int = 72,
) -> str:
    if asset.type != "image" or not asset.origin_key:
        raise api_error(400, "not_image_asset", "Only image assets can have thumbnails")
    if asset.thumb_key and not force:
        return asset.thumb_key
    thumb_key = cos_key(storage, f"thumb/{asset.id}.webp")
    operations = {
        "is_pic_info": 1,
        "rules": [
            {
                "fileid": thumb_key,
                "rule": f"imageMogr2/thumbnail/{max_size}x{max_size}>/strip/format/webp/quality/{quality}",
            }
        ],
    }
    try:
        _, data = client_for(storage).ci_image_process(
            Bucket=storage.bucket,
            Key=asset.origin_key,
            PicOperations=json.dumps(operations, ensure_ascii=False),
        )
    except Exception as exc:
        raise api_error(400, "cos_thumbnail_failed", f"Failed to generate COS thumbnail: {exc}") from exc

    image_info = (
        data.get("OriginalInfo", {})
        .get("ImageInfo", {})
        if isinstance(data, dict)
        else {}
    )
    try:
        asset.width = int(image_info.get("Width") or asset.width or 0)
        asset.height = int(image_info.get("Height") or asset.height or 0)
    except (TypeError, ValueError):
        pass
    asset.thumb_key = thumb_key
    return thumb_key
