select
    article_key,
    published_at,
    published_date,
    observed_at,
    observation_date,
    first_seen_at,
    last_seen_at,
    fetched_at
from {{ ref('all_news_mart_articles') }}
where datetime(observed_at) is null
   or date(observation_date) is null
   or datetime(first_seen_at) is null
   or datetime(last_seen_at) is null
   or datetime(fetched_at) is null
   or datetime(first_seen_at) > datetime(last_seen_at)
   or published_date is not date(published_at)
   or observation_date is not date(observed_at)
   or fetched_at is not last_seen_at
