/* code_comment_style: English, explanation_style: Vietnamese */
/* Staging model to flatten and extract core fields from the raw JSONB payload */

{{ config(materialized='view') }}

WITH base_data AS (
    SELECT
        job_id,
        source_platform,
        url,
        file_name,
        extracted_at,
        -- Reference the dbt source declared in sources.yml
        raw_payload
    FROM {{ source('postgres_raw', 'raw_jobs') }}
)

SELECT
    job_id,
    source_platform,
    url,
    file_name,
    extracted_at,
    
    -- Extract direct text fields from JSONB using ->> operator
    raw_payload->>'title' AS job_title,
    
    -- Extract nested object fields (e.g., Company Name)
    raw_payload->'hiringOrganization'->>'name' AS company_name,
    
    -- Extract location metadata safely
    raw_payload->'jobLocation' -> 0 ->'address'->>'addressLocality' AS location,
    
    -- Keep salary sub-object as JSONB for advanced downstream parsing
    raw_payload->'baseSalary' AS raw_salary_object

FROM base_data