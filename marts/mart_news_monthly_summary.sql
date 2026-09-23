select
    published_year,
    published_month,
    normalized_news_type,
    count(*) as article_count,
    min(published_date) as first_publication_date,
    max(published_date) as latest_publication_date,
    count(distinct published_date) as active_publication_days
from {{ ref('int_news_articles_enriched') }}
group by
    published_year,
    published_month,
    normalized_news_type
