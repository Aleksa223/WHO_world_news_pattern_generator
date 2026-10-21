with articles as (
    select
        coalesce(
            date(gdelt_seen_at),
            date(published_at),
            date(first_seen_at)
        ) as observation_date,
        coalesce(nullif(trim(source_country), ''), 'Unknown') as source_country,
        coalesce(nullif(trim(category), ''), 'uncategorized') as category,
        lower(trim(title)) as normalized_title,
        source,
        coalesce(gdelt_seen_at, published_at, first_seen_at) as observed_at
    from {{ ref('economic_stg_articles') }}
),

country_counts as (
    select
        observation_date,
        source_country,
        category,
        count(*) as article_count,
        count(distinct normalized_title) as unique_story_count,
        count(*) - count(distinct normalized_title) as duplicate_copy_count,
        count(distinct source) as source_count,
        min(observed_at) as first_observed_at,
        max(observed_at) as last_observed_at
    from articles
    group by
        observation_date,
        source_country,
        category
),

daily_totals as (
    select
        observation_date,
        sum(article_count) as daily_article_count
    from country_counts
    group by observation_date
)

select
    country_counts.observation_date
        || ':' || lower(replace(country_counts.source_country, ' ', '_'))
        || ':' || country_counts.category as summary_key,
    country_counts.observation_date,
    country_counts.source_country,
    country_counts.category,
    country_counts.article_count,
    country_counts.unique_story_count,
    country_counts.duplicate_copy_count,
    country_counts.source_count,
    daily_totals.daily_article_count,
    round(
        100.0 * country_counts.article_count / daily_totals.daily_article_count,
        2
    ) as daily_article_share_percentage,
    country_counts.first_observed_at,
    country_counts.last_observed_at
from country_counts
inner join daily_totals
    on country_counts.observation_date = daily_totals.observation_date
