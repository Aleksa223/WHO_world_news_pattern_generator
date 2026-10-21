{{ config(materialized='table') }}

with recursive source_titles as (
    select
        cast(id as text) as article_id,
        coalesce(
            date(gdelt_seen_at),
            date(published_at),
            date(first_seen_at)
        ) as observation_date,
        title,
        lower(trim(title)) as normalized_title,
        url,
        coalesce(nullif(trim(source), ''), 'Unknown') as source,
        coalesce(
            nullif(trim(source_country), ''),
            'Unknown'
        ) as publisher_country,
        coalesce(nullif(trim(category), ''), 'uncategorized') as category,
        coalesce(gdelt_seen_at, published_at, first_seen_at) as observed_at,
        feed_rank
    from {{ ref('economic_stg_articles') }}
    where nullif(trim(title), '') is not null
),

title_characters (
    article_id,
    observation_date,
    title,
    normalized_title,
    url,
    source,
    publisher_country,
    category,
    observed_at,
    feed_rank,
    character_position,
    tokenized_title
) as (
    select
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        1 as character_position,
        '' as tokenized_title
    from source_titles

    union all

    select
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        character_position + 1,
        tokenized_title || case
            when lower(substr(title, character_position, 1))
                glob '[a-z0-9]'
                then lower(substr(title, character_position, 1))
            else ' '
        end
    from title_characters
    where character_position <= length(title)
),

normalized_titles as (
    select
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        trim(tokenized_title) as tokenized_title
    from title_characters
    where character_position = length(title) + 1
),

split_words (
    article_id,
    observation_date,
    title,
    normalized_title,
    url,
    source,
    publisher_country,
    category,
    observed_at,
    feed_rank,
    remaining_title,
    title_word
) as (
    select
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        tokenized_title || ' ' as remaining_title,
        cast(null as text) as title_word
    from normalized_titles

    union all

    select
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        ltrim(substr(remaining_title, instr(remaining_title, ' ') + 1)),
        substr(remaining_title, 1, instr(remaining_title, ' ') - 1)
    from split_words
    where remaining_title <> ''
),

candidate_words as (
    select distinct
        article_id,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        publisher_country,
        category,
        observed_at,
        feed_rank,
        trim(title_word) as title_word
    from split_words
    where trim(title_word) <> ''
      and trim(title_word) not glob '*[0-9]*'
),

mapped_words as (
    select
        candidate_words.*,
        coalesce(
            nullif(lower(trim(topic_map.topic)), ''),
            candidate_words.title_word
        ) as topic,
        topic_map.word is not null as is_mapped
    from candidate_words
    left join {{ ref('economic_title_topic_map') }} as topic_map
        on candidate_words.title_word = lower(trim(topic_map.word))
),

filtered_words as (
    select *
    from mapped_words
    where (
        length(title_word) >= 4
        or is_mapped = 1
    )
      and not exists (
          select 1
          from {{ ref('economic_title_stopwords') }} as stopwords
          where lower(trim(stopwords.word)) = mapped_words.title_word
      )
)

select
    article_id || ':' || title_word as word_key,
    article_id,
    observation_date,
    title,
    normalized_title,
    title_word,
    topic,
    is_mapped,
    url,
    source,
    publisher_country,
    category,
    observed_at,
    feed_rank
from filtered_words
