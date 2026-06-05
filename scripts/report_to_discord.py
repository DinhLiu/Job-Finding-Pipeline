# code_comment_style: English, explanation_style: Vietnamese
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
def fetch_clean_jobs_and_notify():
    """
    Connects to the materialized dbt layer, extracts high-quality analytics insights, and posts to Discord
    """
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
        
        # Query 1: Get total count using the correct 'extracted_at' column
        count_query = """
            SELECT COUNT(*) as total 
            FROM analytics.dim_job_postings 
            WHERE DATE(extracted_at) = CURRENT_DATE;
        """
        cursor.execute(count_query)
        total_clean_jobs = cursor.fetchone()["total"]
        
        if total_clean_jobs == 0:
            print("No new clean jobs found for today. Skipping notification.")
            return

        # Query 2: Fetch Top 3 jobs matching exact Postgres columns: job_title, company_name, url, salary_max
        jobs_query = """
            SELECT job_title, company_name, url, salary_min, salary_max, salary_currency 
            FROM analytics.dim_job_postings 
            WHERE DATE(extracted_at) = CURRENT_DATE
            ORDER BY salary_max DESC NULLS LAST 
            LIMIT 10;
        """
        cursor.execute(jobs_query)
        top_jobs = cursor.fetchall()
        
        fields = []
        for idx, job in enumerate(top_jobs, 1):
            title = job.get("job_title") or "N/A"
            company = job.get("company_name") or "N/A"
            link = job.get("url") or "https://google.com"
            
            # Format salary display based on min-max values smoothly
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
                "name": f"🔥 {idx}. {title}",
                "value": f"**Công ty:** {company}\n**Mức lương tinh lọc:** {salary_display}\n🔗 [Xem chi tiết chiêu mộ]({link})",
                "inline": False
            })
            
        payload = {
            "username": "dbt Analytics Bot",
            "avatar_url": "https://docs.getdbt.com/img/dbt-logo-light.svg",
            "embeds": [{
                "title": "📊 BÁO CÁO VIỆC LÀM ĐÃ QUA LÀM SẠCH & PHÂN TÍCH (dbt)",
                "description": f"Mô hình dữ liệu dbt đã hoàn tất chạy! Phát hiện **{total_clean_jobs}** vị trí tuyển dụng đạt chuẩn chất lượng (đã lọc trùng và chuẩn hóa).",
                "color": 16747520, # Distinct dbt Orange color code
                "fields": fields,
                "footer": {
                    "text": "Đại lý Điều phối Trung tâm • Airflow Core Layer"
                },
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print("Successfully dispatched dbt clean data report to Discord!")
        
    except Exception as error:
        print(f"Error executing reporting pipeline: {error}")
        raise error
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    fetch_clean_jobs_and_notify()