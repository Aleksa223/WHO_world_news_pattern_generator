with articles as (
    select
        id,
        coalesce(
            date(gdelt_seen_at),
            date(published_at),
            date(first_seen_at)
        ) as observation_date,
        title,
        lower(trim(title)) as normalized_title,
        url,
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
            partition by observation_date, normalized_title, category
            order by
                observed_at desc,
                feed_rank,
                id
        ) as example_rank
    from articles
),

title_counts as (
    select
        observation_date,
        normalized_title,
        category,
        max(case when example_rank = 1 then title end) as title,
        max(case when example_rank = 1 then url end) as example_url,
        max(case when example_rank = 1 then source end) as example_source,
        count(*) as article_count,
        count(distinct source) as source_count,
        count(distinct source_country) as publisher_country_count,
        min(feed_rank) as best_feed_rank,
        min(observed_at) as first_observed_at,
        max(observed_at) as last_observed_at
    from ranked_articles
    group by
        observation_date,
        normalized_title,
        category
),

daily_totals as (
    select
        observation_date,
        sum(article_count) as daily_article_count
    from title_counts
    group by observation_date
),

ranked_titles as (
    select
        title_counts.*,
        daily_totals.daily_article_count,
        round(
            100.0 * title_counts.article_count
                / daily_totals.daily_article_count,
            2
        ) as article_share_percentage,
        row_number() over (
            partition by title_counts.observation_date
            order by
                title_counts.article_count desc,
                title_counts.source_count desc,
                title_counts.publisher_country_count desc,
                title_counts.best_feed_rank,
                title_counts.normalized_title
        ) as title_rank
    from title_counts
    inner join daily_totals
        on title_counts.observation_date = daily_totals.observation_date
)

select
    observation_date
        || ':' || category
        || ':' || normalized_title as title_key,
    observation_date,
    title_rank,
    title,
    normalized_title,
    category,
    article_count,
    source_count,
    publisher_country_count,
    daily_article_count,
    article_share_percentage,
    example_url,
    example_source,
    best_feed_rank,
    first_observed_at,
    last_observed_at
from ranked_titles
where title_rank <= 10
