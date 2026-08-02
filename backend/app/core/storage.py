"""boto3 S3 client factory — identical code path for MinIO (local) and
Cloudflare R2 (prod); only env vars differ."""

import boto3
from botocore.config import Config

from app.core.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def check_storage() -> bool:
    """Cheap connectivity check used by /health."""
    client = get_s3_client()
    client.head_bucket(Bucket=settings.s3_bucket)
    return True
