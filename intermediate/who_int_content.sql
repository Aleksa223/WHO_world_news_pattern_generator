with combined_content as (
    select
        'news' as content_type,
        'publication' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_news') }}

    union all

    select
        'statement' as content_type,
        'publication' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_statements') }}

    union all

    select
        'speech' as content_type,
        'publication' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_speech') }}

    union all

    select
        'commentary' as content_type,
        'publication' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_commentary') }}

    union all

    select
        'feature_story' as content_type,
        'publication' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_stories') }}

    union all

    select
        'event' as content_type,
        'event_start' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_events') }}

    union all

    select
        'campaign' as content_type,
        'unavailable' as date_type,
        id,
        title,
        news_type,
        published_at,
        formatted_date,
        url,
        first_seen_at,
        last_seen_at
    from {{ ref('who_stg_campaign') }}
)

select
    content_type || ':' || id as content_key,
    content_type,
    id,
    title,
    trim(news_type) as news_type,
    lower(trim(news_type)) as normalized_news_type,
    date_type,
    datetime(published_at) as published_at,
    date(published_at) as published_date,
    cast(strftime('%Y', published_at) as integer) as published_year,
    cast(strftime('%m', published_at) as integer) as published_month,
    formatted_date,
    url,
    case content_type
        when 'news' then replace(url, 'https://www.who.int/news/item/', '')
        when 'statement' then replace(url, 'https://www.who.int/news/item/', '')
        when 'speech' then replace(
            url,
            'https://www.who.int/news-room/speeches/item/',
            ''
        )
        when 'commentary' then replace(
            url,
            'https://www.who.int/news-room/commentaries/detail/',
            ''
        )
        when 'feature_story' then replace(
            url,
            'https://www.who.int/news-room/feature-stories/detail/',
            ''
        )
        when 'event' then replace(
            url,
            'https://www.who.int/news-room/events/detail/',
            ''
        )
        when 'campaign' then replace(url, 'https://www.who.int/campaigns/', '')
    end as content_slug,
    datetime(first_seen_at) as first_seen_at,
    datetime(last_seen_at) as last_seen_at
from combined_content
