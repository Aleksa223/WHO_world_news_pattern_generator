with staged_news as (
    select *
    from {{ ref('who_stg_stories') }}
)

select
    id,
    title,
    lower(trim(news_type)) as normalized_news_type,
    datetime(published_at) as published_at,
    date(published_at) as published_date,
    cast(strftime('%Y', published_at) as integer) as published_year,
    cast(strftime('%m', published_at) as integer) as published_month,
    formatted_date,
    url,
    substr(
    replace(url, 'https://www.who.int/news/item/', ''),
    11
    ) as article_slug,
    datetime(first_seen_at) as first_seen_at,
    datetime(last_seen_at) as last_seen_at
from staged_news
