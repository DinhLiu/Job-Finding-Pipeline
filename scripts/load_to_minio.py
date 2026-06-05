from datetime import datetime
import io
import json
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

DEFAULT_BUCKET_NAME = "raw-job-payloads"


def get_minio_client():
    """Create an S3-compatible client for MinIO."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    minio_endpoint = os.getenv("MINIO_ENDPOINT_URL")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")

    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket_exists(bucket_name: str = DEFAULT_BUCKET_NAME) -> None:
    """Create the raw bucket if it does not exist yet."""
    s3 = get_minio_client()
    try:
        s3.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        status_code = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status_code == 404:
            s3.create_bucket(Bucket=bucket_name)
            return
        raise


def build_raw_object_key(source_name: str, file_name: str = "output.json") -> str:
    """Build a partitioned object key such as itviec/2026/06/05/output.json."""
    current_date = datetime.now()
    return f"{source_name}/{current_date.strftime('%Y/%m/%d')}/{file_name}"


def upload_json_to_minio(
    records: list[dict],
    source_name: str,
    *,
    bucket_name: str = DEFAULT_BUCKET_NAME,
    file_name: str = "output.json",
) -> str:
    """Upload crawled JSON records directly to MinIO without writing local files."""
    ensure_bucket_exists(bucket_name)
    object_key = build_raw_object_key(source_name, file_name)
    payload = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")

    print(f"Uploading {len(records)} {source_name} records to s3://{bucket_name}/{object_key}...")
    get_minio_client().put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=io.BytesIO(payload),
        ContentLength=len(payload),
        ContentType="application/json",
    )
    print("Upload complete.")
    return object_key


if __name__ == "__main__":
    raise SystemExit("Use scripts/crawler.py to crawl and upload data directly to MinIO.")
