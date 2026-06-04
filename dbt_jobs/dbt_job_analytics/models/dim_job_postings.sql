{{ config(materialized='table') }}

WITH int_data AS (
    SELECT * FROM {{ ref('int_job_postings') }}
)

SELECT
    -- Surrogate Key or natural primary key for the dimension
    job_id,
    source_platform,
    url,
    job_title,
    company_name,
    clean_location AS location,
    is_negotiable,
    salary_currency,
    salary_min,
    salary_max,
    salary_avg,
    normalized_salary_vnd,
    extracted_at,

    -- Categorize job levels based on common keywords in the title for better analytical grouping
    CASE 
        WHEN LOWER(job_title) LIKE '%intern%' THEN 'Internship'
        WHEN LOWER(job_title) LIKE '%fresher%' THEN 'Fresher'
        WHEN LOWER(job_title) LIKE '%junior%' THEN 'Junior'
        WHEN LOWER(job_title) LIKE '%senior%' THEN 'Senior'
        WHEN LOWER(job_title) LIKE '%lead%' OR LOWER(job_title) LIKE '%principal%' THEN 'Lead/Principal'
        WHEN LOWER(job_title) LIKE '%manager%' THEN 'Management'
        ELSE 'Mid/Unspecified'
    END AS job_level

FROM int_data