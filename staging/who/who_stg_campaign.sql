{{ config(materialized='table') }}

select
    id,
    title,
    campaign_type as news_type,
    cast(null as text) as published_at,
    cast (null as text) as formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('campaign_news', 'articles') }}
where lower(coalesce(campaign_type, '')) like '%campaigns%'
