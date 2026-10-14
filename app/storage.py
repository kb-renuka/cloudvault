import hashlib

import boto3
from botocore.client import Config

from app.config import settings

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
            config=Config(signature_version="s3v4"),
        )
    return _client


def ensure_bucket() -> None:
    s3 = client()
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in existing:
        s3.create_bucket(Bucket=settings.s3_bucket)


def upload_fileobj(fileobj, key: str) -> None:
    client().upload_fileobj(fileobj, settings.s3_bucket, key)


def sha256_and_size(key: str) -> tuple[str, int]:
    """Stream an object from S3 and compute its SHA-256 without loading it into memory."""
    body = client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"]
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: body.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def copy_object(src_key: str, dst_key: str) -> None:
    client().copy_object(
        Bucket=settings.s3_bucket,
        Key=dst_key,
        CopySource={"Bucket": settings.s3_bucket, "Key": src_key},
    )


def delete_object(key: str) -> None:
    client().delete_object(Bucket=settings.s3_bucket, Key=key)


def presigned_url(key: str) -> str:
    return client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presign_expiry_seconds,
    )
