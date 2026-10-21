{{ config(materialized='table') }}

select
    id,
    title,
    story_type as news_type,
    published_at,
    formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('stories_news', 'articles') }}
where lower(coalesce(story_type, '')) like '%stories%'
