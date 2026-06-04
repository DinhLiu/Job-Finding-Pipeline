# code_comment_style: English, explanation_style: Vietnamese
import json
import os
import psycopg2
from psycopg2.extras import execute_values

def load_raw_jobs_to_postgres(file_path: str, source_platform: str):
    """
    Reads the crawler JSON output file, splits the array into individual records,
    and performs a structural UPSERT into staging.raw_jobs inside PostgreSQL.
    """
    # 1. Validate file existence before opening connection
    if not os.path.exists(file_path):
        print(f"Error: Target file not found at {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            jobs_list = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON file {file_path}. Details: {e}")
            return

    if not jobs_list:
        print(f"Warning: The file {file_path} is empty. No records to load.")
        return

    # 2. Establish database connection (Update credentials based on Docker configuration)
    db_params = {
        "host": "127.0.0.1",
        "database": "job_analytics",
        "user": "warehouse_user",
        "password": "warehouse_password",
        "port": "5433"
    }

    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Extract the base file name for traceability logging inside database columns
        file_name = os.path.basename(file_path)
        
        # 3. Transform JSON array elements into database row tuples
        records_to_insert = []
        for item in jobs_list:
            job_id = item.get("job_id")
            url = item.get("url")
            raw_payload = item.get("raw_payload")
            
            # Defensive check: Ensure critical fields exist before pushing to database
            if not job_id or not raw_payload:
                print(f"Skipping corrupt record missing job_id or raw_payload in file: {file_name}")
                continue
                
            records_to_insert.append((
                str(job_id),
                source_platform.strip().lower(),
                url,
                file_name,
                json.dumps(raw_payload) # Cast payload dictionary back to valid JSON string format
            ))

        # 4. Define SQL Upsert query aligning with the composite primary key configuration
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

        # 5. Execute bulk insertion efficiently using execute_values
        print(f"Loading {len(records_to_insert)} rows from '{source_platform}' into staging.raw_jobs...")
        execute_values(cursor, upsert_query, records_to_insert)
        
        conn.commit()
        print(f"Successfully loaded and committed data into PostgreSQL database.")

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
    # Test executions targeting your exact local outputs
    # Ensure you have executed your crawlers first to generate these JSON files
    print("Loading data from IT Viec....")
    load_raw_jobs_to_postgres(file_path="itviec_output.json", source_platform="itviec")
    
    print("\nLoading data from Top CV")
    load_raw_jobs_to_postgres(file_path="topcv_output.json", source_platform="topcv")