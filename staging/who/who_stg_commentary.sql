{{ config(materialized='table') }}

select
    id,
    title,
    commentary_type as news_type,
    published_at,
    formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('commentary_news', 'articles') }}
where lower(coalesce(commentary_type, '')) like '%commentaries%'
