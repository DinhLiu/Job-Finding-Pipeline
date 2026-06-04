FROM apache/airflow:2.10.0

# Switch to root user to install compiler dependencies safely
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user to install Python packages inside the virtual environment
USER airflow
RUN pip install --no-cache-dir dbt-core==1.8.0 dbt-postgres==1.8.0 beautifulsoup4 playwright playwright-stealth