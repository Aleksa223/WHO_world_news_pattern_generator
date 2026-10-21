{{ config(materialized='table') }}

with recursive source_titles as (
    select
        content_key as article_id,
        content_key,
        content_type,
        coalesce(
            published_date,
            date(first_seen_at),
            date(last_seen_at)
        ) as observation_date,
        title,
        lower(trim(title)) as normalized_title,
        url,
        'who.int' as source,
        content_type as category,
        coalesce(published_at, last_seen_at, first_seen_at) as observed_at,
        0 as feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at
    from {{ ref('who_int_content') }}
    where nullif(trim(title), '') is not null
),

title_characters (
    article_id,
    content_key,
    content_type,
    observation_date,
    title,
    normalized_title,
    url,
    source,
    category,
    observed_at,
    feed_rank,
    date_type,
    published_date,
    published_at,
    first_seen_at,
    last_seen_at,
    character_position,
    tokenized_title
) as (
    select
        article_id,
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
        1 as character_position,
        '' as tokenized_title
    from source_titles

    union all

    select
        article_id,
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
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
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
        trim(tokenized_title) as tokenized_title
    from title_characters
    where character_position = length(title) + 1
),

split_words (
    article_id,
    content_key,
    content_type,
    observation_date,
    title,
    normalized_title,
    url,
    source,
    category,
    observed_at,
    feed_rank,
    date_type,
    published_date,
    published_at,
    first_seen_at,
    last_seen_at,
    remaining_title,
    title_word
) as (
    select
        article_id,
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
        tokenized_title || ' ' as remaining_title,
        cast(null as text) as title_word
    from normalized_titles

    union all

    select
        article_id,
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
        ltrim(substr(remaining_title, instr(remaining_title, ' ') + 1)),
        substr(remaining_title, 1, instr(remaining_title, ' ') - 1)
    from split_words
    where remaining_title <> ''
),

candidate_words as (
    select distinct
        article_id,
        content_key,
        content_type,
        observation_date,
        title,
        normalized_title,
        url,
        source,
        category,
        observed_at,
        feed_rank,
        date_type,
        published_date,
        published_at,
        first_seen_at,
        last_seen_at,
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
        ) as canonical_topic,
        topic_map.word is not null as is_mapped
    from candidate_words
    left join {{ ref('who_title_topic_map') }} as topic_map
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
          from {{ ref('who_topic_stopwords') }} as stopwords
          where lower(trim(stopwords.word)) = mapped_words.title_word
      )
)

select
    article_id || ':' || title_word as word_key,
    article_id || ':' || title_word as topic_key,
    article_id,
    content_key,
    content_type,
    observation_date,
    title,
    normalized_title,
    title_word,
    title_word as topic,
    canonical_topic,
    is_mapped,
    url,
    source,
    category,
    observed_at,
    feed_rank,
    date_type,
    published_date,
    published_at,
    first_seen_at,
    last_seen_at
from filtered_words
