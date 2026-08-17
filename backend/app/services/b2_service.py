"""
app/services/b2_service.py
---------------------------
Thin wrapper around boto3 for Backblaze B2 uploads and downloads.

FastAPI calls upload_file() to store CSVs.
Celery workers call download_file() to retrieve them for processing.
Neither touches local disk as a shared store — B2 is the shared filesystem.
"""

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from app.core.config import settings

_s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.B2_ENDPOINT_URL}",
    aws_access_key_id=settings.B2_APPLICATION_KEY_ID,
    aws_secret_access_key=settings.B2_APPLICATION_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-west-004", # Region is usually ignored by B2 but required by boto3
)


def upload_file(file_bytes: bytes, b2_key: str) -> str:
    """
    Upload raw bytes to B2. Returns the B2 key on success.
    Raises RuntimeError on failure.
    """
    try:
        _s3.put_object(
            Bucket=settings.B2_BUCKET_NAME,
            Key=b2_key,
            Body=file_bytes,
            ContentType="text/csv",
        )
        return b2_key
    except ClientError as exc:
        raise RuntimeError(f"B2 upload failed for key '{b2_key}': {exc}") from exc


def download_file(b2_key: str) -> bytes:
    """
    Download a file from B2 and return its raw bytes.
    Raises RuntimeError if the key does not exist.
    """
    try:
        response = _s3.get_object(Bucket=settings.B2_BUCKET_NAME, Key=b2_key)
        return response["Body"].read()
    except ClientError as exc:
        raise RuntimeError(f"B2 download failed for key '{b2_key}': {exc}") from exc
