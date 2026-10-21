with articles as (
    select
        id,
        coalesce(
            date(gdelt_seen_at),
            date(published_at),
            date(first_seen_at)
        ) as observation_date,
        title,
        source,
        coalesce(nullif(trim(source_country), ''), 'Unknown') as source_country,
        coalesce(nullif(trim(category), ''), 'uncategorized') as category,
        coalesce(gdelt_seen_at, published_at, first_seen_at) as observed_at,
        feed_rank
    from {{ ref('economic_stg_articles') }}
),

ranked_articles as (
    select
        *,
        row_number() over (
            partition by observation_date, source, source_country, category
            order by
                observed_at desc,
                feed_rank,
                id
        ) as example_rank
    from articles
),

source_counts as (
    select
        observation_date,
        source,
        source_country,
        category,
        count(*) as article_count,
        max(case when example_rank = 1 then title end) as example_title,
        min(observed_at) as first_observed_at,
        max(observed_at) as last_observed_at
    from ranked_articles
    group by
        observation_date,
        source,
        source_country,
        category
),

daily_totals as (
    select
        observation_date,
        sum(article_count) as daily_article_count
    from source_counts
    group by observation_date
),

ranked_sources as (
    select
        source_counts.*,
        daily_totals.daily_article_count,
        round(
            100.0 * source_counts.article_count
                / daily_totals.daily_article_count,
            2
        ) as article_share_percentage,
        row_number() over (
            partition by source_counts.observation_date
            order by
                source_counts.article_count desc,
                source_counts.last_observed_at desc,
                source_counts.source,
                source_counts.source_country
        ) as source_rank
    from source_counts
    inner join daily_totals
        on source_counts.observation_date = daily_totals.observation_date
)

select
    observation_date
        || ':' || source
        || ':' || lower(replace(source_country, ' ', '_')) as source_key,
    observation_date,
    source_rank,
    source,
    source_country,
    category,
    article_count,
    daily_article_count,
    article_share_percentage,
    example_title,
    first_observed_at,
    last_observed_at
from ranked_sources
where source_rank <= 10
