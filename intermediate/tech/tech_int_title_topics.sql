{{ config(materialized='table') }}

with recursive source_titles as (
    select
        cast(id as text) as article_id,
        cast(id as text) as story_id,
        coalesce(
            date(published_at),
            date(first_seen_at)
        ) as observation_date,
        title,
        lower(trim(title)) as normalized_title,
        replace(
            replace(
                replace(
                    replace(
                        replace(lower(title), 'node.js', 'nodejs'),
                        '.net', 'dotnet'
                    ),
                    'c++', 'cpp'
                ),
                'c#', 'csharp'
            ),
            'f#', 'fsharp'
        ) as prepared_title,
        url,
        discussion_url,
        coalesce(nullif(lower(trim(source)), ''), 'unknown') as source,
        coalesce(nullif(lower(trim(category)), ''), 'uncategorized') as category,
        coalesce(published_at, last_seen_at, first_seen_at) as observed_at,
        feed_rank,
        coalesce(nullif(lower(trim(feed)), ''), 'unknown') as feed,
        author,
        coalesce(score, 0) as score,
        coalesce(comment_count, 0) as comment_count
    from {{ ref('tech_stg_story') }}
    where nullif(trim(title), '') is not null
),

title_characters (
    article_id,
    story_id,
    observation_date,
    title,
    normalized_title,
    prepared_title,
    url,
    discussion_url,
    source,
    category,
    observed_at,
    feed_rank,
    feed,
    author,
    score,
    comment_count,
    character_position,
    tokenized_title
) as (
    select
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        prepared_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
        1 as character_position,
        '' as tokenized_title
    from source_titles

    union all

    select
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        prepared_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
        character_position + 1,
        tokenized_title || case
            when substr(prepared_title, character_position, 1)
                glob '[a-z0-9]'
                then substr(prepared_title, character_position, 1)
            else ' '
        end
    from title_characters
    where character_position <= length(prepared_title)
),

normalized_titles as (
    select
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
        trim(tokenized_title) as tokenized_title
    from title_characters
    where character_position = length(prepared_title) + 1
),

split_words (
    article_id,
    story_id,
    observation_date,
    title,
    normalized_title,
    url,
    discussion_url,
    source,
    category,
    observed_at,
    feed_rank,
    feed,
    author,
    score,
    comment_count,
    remaining_title,
    title_word
) as (
    select
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
        tokenized_title || ' ' as remaining_title,
        cast(null as text) as title_word
    from normalized_titles

    union all

    select
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
        ltrim(substr(remaining_title, instr(remaining_title, ' ') + 1)),
        substr(remaining_title, 1, instr(remaining_title, ' ') - 1)
    from split_words
    where remaining_title <> ''
),

candidate_words as (
    select distinct
        article_id,
        story_id,
        observation_date,
        title,
        normalized_title,
        url,
        discussion_url,
        source,
        category,
        observed_at,
        feed_rank,
        feed,
        author,
        score,
        comment_count,
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
    left join {{ ref('tech_title_topic_map') }} as topic_map
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
          from {{ ref('tech_title_stopwords') }} as stopwords
          where lower(trim(stopwords.word)) = mapped_words.title_word
      )
)

select
    article_id || ':' || title_word as word_key,
    article_id,
    story_id,
    observation_date,
    title,
    normalized_title,
    title_word,
    topic,
    topic as canonical_topic,
    is_mapped,
    url,
    discussion_url,
    source,
    category,
    observed_at,
    feed_rank,
    feed,
    author,
    score,
    comment_count
from filtered_words
