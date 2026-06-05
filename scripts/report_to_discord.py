import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from datetime import datetime
import os
import time
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

load_dotenv(dotenv_path=ENV_PATH)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

def fetch_clean_jobs_and_notify():
    connection_config = {
        "host": os.getenv('POSTGRES_HOST'),
        "database": os.getenv('POSTGRES_DB'),
        "user": os.getenv('POSTGRES_USER'),
        "password": os.getenv('POSTGRES_PASSWORD'),
        "port": os.getenv('POSTGRES_PORT')
    }
    
    try:
        conn = psycopg2.connect(**connection_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query 1: Calculate the total count of 'Net-New' jobs within this session
        count_query = """
            WITH JobFirstSeen AS (
                SELECT url, MIN(extracted_at) as first_seen_time
                FROM analytics.dim_job_postings
                GROUP BY url
            )
            SELECT COUNT(*) as total 
            FROM JobFirstSeen 
            WHERE first_seen_time >= NOW() - INTERVAL '30 minutes';
        """
        cursor.execute(count_query)
        total_clean_jobs = cursor.fetchone()["total"]
        
        if total_clean_jobs == 0:
            print("No new clean jobs found for this session. Skipping notification.")
            return

        jobs_query = """
            WITH JobFirstSeen AS (
                SELECT 
                    job_title, 
                    company_name, 
                    url, 
                    salary_min, 
                    salary_max, 
                    salary_currency,
                    MIN(extracted_at) OVER (PARTITION BY url) as first_seen_time
                FROM analytics.dim_job_postings
            ),
            DeduplicatedNewJobs AS (
                SELECT DISTINCT job_title, company_name, url, salary_min, salary_max, salary_currency
                FROM JobFirstSeen
                WHERE first_seen_time >= NOW() - INTERVAL '30 minutes'
            )
            SELECT * FROM DeduplicatedNewJobs
            ORDER BY salary_max DESC NULLS LAST;
        """
        cursor.execute(jobs_query)
        all_new_jobs = cursor.fetchall()
        
        CHUNK_SIZE = 10
        total_batches = (len(all_new_jobs) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * CHUNK_SIZE
            end_idx = start_idx + CHUNK_SIZE
            current_chunk = all_new_jobs[start_idx:end_idx]
            
            fields = []
            for idx, job in enumerate(current_chunk, start=start_idx + 1):
                title = job.get("job_title") or "N/A"
                company = job.get("company_name") or "N/A"
                link = job.get("url") or "https://google.com"
                
                s_min = job.get("salary_min")
                s_max = job.get("salary_max")
                currency = job.get("salary_currency") or "VND"
                
                if s_min and s_max:
                    salary_display = f"{int(s_min):,} - {int(s_max):,} {currency}"
                elif s_max:
                    salary_display = f"Up to {int(s_max):,} {currency}"
                else:
                    salary_display = "Thỏa thuận"
                
                fields.append({
                    "name": f"{idx}. {title}",
                    "value": f"Công ty: {company}\nMức lương tinh lọc: {salary_display}\n[Chi tiết tại]({link})",
                    "inline": False
                })
            
            page_info = f" (Trang {batch_idx + 1}/{total_batches})" if total_batches > 1 else ""
                
            payload = {
                "username": "Job Announcement Bot",
                "avatar_url": "https://docs.getdbt.com/img/dbt-logo-light.svg",
                "embeds": [{
                    "title": f"BÁO CÁO VIỆC LÀM MỚI{page_info}",
                    "description": f"Phát hiện **{total_clean_jobs}** vị trí tuyển dụng.",
                    "color": 16747520,
                    "fields": fields,
                    "footer": {
                        "text": "Airflow Core Layer"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }
            
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            print(f"Successfully dispatched batch {batch_idx + 1}/{total_batches} to Discord!")
            
            if batch_idx < total_batches - 1:
                time.sleep(1.5)
        
    except Exception as error:
        print(f"Error executing reporting pipeline: {error}")
        raise error
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    fetch_clean_jobs_and_notify()