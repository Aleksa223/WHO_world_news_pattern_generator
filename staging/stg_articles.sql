select
    id,
    title,
    news_type,
    published_at,
    formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('who_news', 'articles') }}
where lower(coalesce(news_type, '')) like '%news%'
