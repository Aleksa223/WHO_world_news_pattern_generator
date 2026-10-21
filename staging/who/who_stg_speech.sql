{{ config(materialized='table') }}

select
    id,
    title,
    speech_type as news_type,
    published_at,
    formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('speech_news', 'articles') }}
where lower(coalesce(speech_type, '')) like '%speeches%'
