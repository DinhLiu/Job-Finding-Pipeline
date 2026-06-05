import json
import os
import psycopg2
from psycopg2.extras import execute_values
from scripts.load_to_minio import DEFAULT_BUCKET_NAME, get_minio_client


def get_latest_raw_object_key(source_platform: str, bucket_name: str = DEFAULT_BUCKET_NAME) -> str | None:
    """Find the newest raw JSON object for a source in MinIO."""
    s3 = get_minio_client()
    paginator = s3.get_paginator("list_objects_v2")
    newest_object = None

    for page in paginator.paginate(Bucket=bucket_name, Prefix=f"{source_platform}/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json") and (
                newest_object is None or obj["LastModified"] > newest_object["LastModified"]
            ):
                newest_object = obj

    return newest_object["Key"] if newest_object else None


def read_json_from_minio(object_key: str, bucket_name: str = DEFAULT_BUCKET_NAME) -> list[dict]:
    """Read a JSON array directly from MinIO."""
    response = get_minio_client().get_object(Bucket=bucket_name, Key=object_key)
    try:
        return json.loads(response["Body"].read().decode("utf-8"))
    finally:
        response["Body"].close()


def load_raw_jobs_to_postgres(source_platform: str, object_key: str | None = None):
    """
    Reads raw crawler records from MinIO, splits the array into individual records,
    and performs a structural UPSERT into staging.raw_jobs inside PostgreSQL.
    """
    bucket_name = os.getenv("MINIO_BUCKET_NAME", DEFAULT_BUCKET_NAME)
    object_key = object_key or get_latest_raw_object_key(source_platform, bucket_name)
    if not object_key:
        print(f"Error: No raw JSON object found in MinIO for source '{source_platform}'")
        return

    try:
        jobs_list = read_json_from_minio(object_key, bucket_name)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse MinIO object s3://{bucket_name}/{object_key}. Details: {e}")
        return

    if not jobs_list:
        print(f"Warning: MinIO object s3://{bucket_name}/{object_key} is empty. No records to load.")
        return

    db_params = {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "database": os.getenv("POSTGRES_DB", "job_analytics"),
        "user": os.getenv("POSTGRES_USER", "warehouse_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "warehouse_password"),
        "port": os.getenv("POSTGRES_PORT", "5433"),
    }

    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()

        records_to_insert = []
        for item in jobs_list:
            job_id = item.get("job_id")
            url = item.get("url")
            raw_payload = item.get("raw_payload")

            if not job_id or not raw_payload:
                print(f"Skipping corrupt record missing job_id or raw_payload in object: {object_key}")
                continue

            records_to_insert.append((
                str(job_id),
                source_platform.strip().lower(),
                url,
                object_key,
                json.dumps(raw_payload),
            ))

        if not records_to_insert:
            print(f"Warning: No valid records found in s3://{bucket_name}/{object_key}.")
            return

        upsert_query = """
            INSERT INTO staging.raw_jobs (job_id, source_platform, url, file_name, raw_payload)
            VALUES %s
            ON CONFLICT (job_id, source_platform)
            DO UPDATE SET
                url = EXCLUDED.url,
                file_name = EXCLUDED.file_name,
                raw_payload = EXCLUDED.raw_payload,
                extracted_at = CURRENT_TIMESTAMP;
        """

        print(
            f"Loading {len(records_to_insert)} rows from s3://{bucket_name}/{object_key} "
            "into staging.raw_jobs..."
        )
        execute_values(cursor, upsert_query, records_to_insert)

        conn.commit()
        print("Successfully loaded and committed data into PostgreSQL database.")

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        print(f"Database operation failed. Transaction rolled back. Details: {e}")
        
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    print("Loading data from ITViec MinIO object...")
    load_raw_jobs_to_postgres(source_platform="itviec")

    print("\nLoading data from TopCV MinIO object...")
    load_raw_jobs_to_postgres(source_platform="topcv")
