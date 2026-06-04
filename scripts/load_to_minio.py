# code_comment_style: English, explanation_style: Vietnamese
from datetime import datetime
import os
import boto3
from botocore.client import Config

def upload_raw_to_minio(file_path: str, source_name: str):
    """Uploads the raw JSON crawler output into the MinIO Data Lake bucket."""
    minio_endpoint = "http://localhost:9000"
    access_key = "admin"
    secret_key = "securepassword123"
    bucket_name = "raw-job-payloads"

    # Initialize MinIO client compatible with AWS S3 API
    s3 = boto3.resource(
        "s3",
        endpoint_url=minio_endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

    # Ensure the bucket exists before uploading
    bucket = s3.Bucket(bucket_name)
    if not bucket.creation_date:
        s3.create_bucket(Bucket=bucket_name)

    # Construct a historical partitioned path: e.g., itviec/2026/06/04/output.json
    current_date = datetime.now()
    destination_path = f"{source_name}/{current_date.strftime('%Y/%m/%d')}/{os.path.basename(file_path)}"

    print(f"Uploading {file_path} to MinIO bucket '{bucket_name}' at '{destination_path}'...")
    bucket.upload_file(file_path, destination_path)
    print("Upload complete.")

if __name__ == "__main__":
    # Test uploading your current output file
    upload_raw_to_minio("itviec_output.json", "itviec")
    upload_raw_to_minio("topcv_output.json", "topcv")