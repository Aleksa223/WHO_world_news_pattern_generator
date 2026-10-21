{{ config(materialized='table') }}

select
    cast(id as text) as id,
    trim(provider) as provider,
    lower(trim(item_type)) as item_type,
    coalesce(nullif(trim(title_english), ''), trim(title)) as title,
    trim(title_original) as title_original,
    coalesce(nullif(trim(title_english), ''), trim(title)) as title_english,
    lower(trim(coalesce(translation_source_language, 'en'))) as translation_source_language,
    lower(trim(translation_status)) as translation_status,
    translation_provider,
    translated_at,
    description,
    keywords,
    snippet,
    url,
    mobile_url,
    image_url,
    'english' as language,
    published_at,
    gdelt_seen_at,
    gdelt_seen_date,
    lower(trim(source)) as source,
    source_country,
    lower(trim(feed)) as feed,
    cast(feed_rank as integer) as feed_rank,
    query,
    lower(trim(category)) as category,
    categories_json,
    first_seen_at,
    last_seen_at
from {{ source('economic_news', 'economic_articles') }}
where (
    lower(replace(trim(coalesce(language, '')), '_', '-')) = 'en'
    or lower(replace(trim(coalesce(language, '')), '_', '-')) like 'en-%'
    or lower(trim(coalesce(language, ''))) like 'english%'
)
  and lower(trim(coalesce(item_type, ''))) = 'article'
  and lower(trim(coalesce(category, ''))) = 'economic'
