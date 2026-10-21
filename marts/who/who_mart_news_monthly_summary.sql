with content_with_period as (
    select
        *,
        case
            when published_date is null then 'Unknown'
            else printf('%04d-%02d', published_year, published_month)
        end as reporting_period
    from {{ ref('who_int_content') }}
)

select
    published_year,
    published_month,
    reporting_period,
    date_type,
    normalized_news_type,
    count(*) as article_count,
    min(published_date) as first_publication_date,
    max(published_date) as latest_publication_date,
    count(distinct published_date) as active_publication_days
from content_with_period
group by
    published_year,
    published_month,
    reporting_period,
    date_type,
    normalized_news_type
