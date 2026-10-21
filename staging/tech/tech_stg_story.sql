{{ config(materialized='table') }}

select
    cast(id as text) as id,
    provider,
    lower(trim(item_type)) as item_type,
    title,
    description,
    keywords,
    snippet,
    url,
    discussion_url,
    image_url,
    language,
    published_at,
    source,
    author,
    cast(score as integer) as score,
    cast(comment_count as integer) as comment_count,
    feed,
    cast(feed_rank as integer) as feed_rank,
    category,
    categories_json,
    first_seen_at,
    last_seen_at
from {{ source('tech_news', 'tech_articles') }}
where lower(trim(coalesce(item_type, ''))) = 'story'
