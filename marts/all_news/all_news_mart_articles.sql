with who_content as (
    select
        'who:' || content_key as article_key,
        cast(id as text) as article_id,
        'who' as news_type,
        'WHO' as provider,
        content_type,
        'health' as topic,
        title,
        lower(trim(title)) as normalized_title,
        url,
        'who.int' as source,
        cast(null as text) as source_country,
        'en' as language,
        date_type,
        datetime(published_at) as published_at,
        date(published_at) as published_date,
        datetime(coalesce(published_at, last_seen_at, first_seen_at))
            as observed_at,
        date(coalesce(published_at, last_seen_at, first_seen_at))
            as observation_date,
        datetime(first_seen_at) as first_seen_at,
        datetime(last_seen_at) as last_seen_at,
        datetime(last_seen_at) as fetched_at
    from {{ ref('who_int_content') }}
),

tech_content as (
    select
        'tech:' || cast(id as text) as article_key,
        cast(id as text) as article_id,
        'tech' as news_type,
        coalesce(nullif(trim(provider), ''), 'Hacker News') as provider,
        item_type as content_type,
        'technology' as topic,
        title,
        lower(trim(title)) as normalized_title,
        url,
        coalesce(
            nullif(lower(trim(source)), ''),
            'news.ycombinator.com'
        ) as source,
        cast(null as text) as source_country,
        nullif(lower(trim(language)), '') as language,
        'publication' as date_type,
        datetime(published_at) as published_at,
        date(published_at) as published_date,
        datetime(coalesce(published_at, last_seen_at, first_seen_at))
            as observed_at,
        date(coalesce(published_at, last_seen_at, first_seen_at))
            as observation_date,
        datetime(first_seen_at) as first_seen_at,
        datetime(last_seen_at) as last_seen_at,
        datetime(last_seen_at) as fetched_at
    from {{ ref('tech_stg_story') }}
),

economic_content as (
    select
        'economic:' || cast(id as text) as article_key,
        cast(id as text) as article_id,
        'economic' as news_type,
        coalesce(nullif(trim(provider), ''), 'GDELT') as provider,
        item_type as content_type,
        'economic' as topic,
        title,
        lower(trim(title)) as normalized_title,
        url,
        coalesce(nullif(lower(trim(source)), ''), 'unknown') as source,
        nullif(trim(source_country), '') as source_country,
        'en' as language,
        'gdelt_observation' as date_type,
        datetime(published_at) as published_at,
        date(published_at) as published_date,
        datetime(
            coalesce(
                gdelt_seen_at,
                published_at,
                last_seen_at,
                first_seen_at
            )
        ) as observed_at,
        date(
            coalesce(
                gdelt_seen_at,
                published_at,
                last_seen_at,
                first_seen_at
            )
        ) as observation_date,
        datetime(first_seen_at) as first_seen_at,
        datetime(last_seen_at) as last_seen_at,
        datetime(last_seen_at) as fetched_at
    from {{ ref('economic_stg_articles') }}
)

select * from who_content
union all
select * from tech_content
union all
select * from economic_content
