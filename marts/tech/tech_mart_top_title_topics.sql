with topic_occurrences as (
    select distinct
        article_id,
        category,
        canonical_topic as topic,
        title,
        normalized_title,
        url,
        source,
        feed,
        observation_date,
        observed_at,
        feed_rank,
        score,
        comment_count
    from {{ ref('tech_int_title_topics') }}
),

ordered_topic_words as (
    select distinct
        category,
        canonical_topic as topic,
        title_word
    from {{ ref('tech_int_title_topics') }}
    order by
        category,
        canonical_topic,
        title_word
),

topic_word_lists as (
    select
        category,
        topic,
        group_concat(title_word, ', ') as grouped_words,
        count(*) as grouped_word_count
    from ordered_topic_words
    group by
        category,
        topic
),

ranked_examples as (
    select
        *,
        row_number() over (
            partition by category, topic
            order by
                observed_at desc,
                feed_rank,
                title,
                article_id
        ) as example_rank
    from topic_occurrences
),

topic_counts as (
    select
        category,
        topic,
        max(case when example_rank = 1 then title end) as example_title,
        max(case when example_rank = 1 then url end) as example_url,
        max(case when example_rank = 1 then source end) as example_source,
        count(distinct article_id) as story_count,
        count(distinct normalized_title) as unique_title_count,
        count(distinct source) as source_count,
        count(distinct feed) as feed_count,
        sum(score) as total_score,
        sum(comment_count) as total_comments,
        min(observation_date) as first_occurrence_date,
        max(observation_date) as last_occurrence_date
    from ranked_examples
    group by
        category,
        topic
),

corpus_totals as (
    select
        coalesce(nullif(lower(trim(category)), ''), 'uncategorized') as category,
        count(*) as corpus_story_count,
        count(distinct lower(trim(title))) as corpus_unique_title_count
    from {{ ref('tech_stg_story') }}
    group by coalesce(nullif(lower(trim(category)), ''), 'uncategorized')
),

ranked_topics as (
    select
        topic_counts.*,
        topic_word_lists.grouped_words,
        topic_word_lists.grouped_word_count,
        corpus_totals.corpus_story_count,
        corpus_totals.corpus_unique_title_count,
        round(
            100.0 * topic_counts.unique_title_count
                / nullif(corpus_totals.corpus_unique_title_count, 0),
            2
        ) as unique_title_percentage,
        round(
            100.0 * topic_counts.story_count
                / nullif(corpus_totals.corpus_story_count, 0),
            2
        ) as story_percentage,
        row_number() over (
            partition by topic_counts.category
            order by
                topic_counts.unique_title_count desc,
                topic_counts.story_count desc,
                topic_counts.source_count desc,
                topic_counts.topic
        ) as topic_rank
    from topic_counts
    inner join topic_word_lists
        on topic_counts.category = topic_word_lists.category
       and topic_counts.topic = topic_word_lists.topic
    inner join corpus_totals
        on topic_counts.category = corpus_totals.category
)

select
    category || ':' || topic as topic_key,
    category,
    topic_rank,
    topic,
    grouped_words,
    grouped_word_count,
    unique_title_count,
    story_count,
    source_count,
    feed_count,
    total_score,
    total_comments,
    corpus_unique_title_count,
    corpus_story_count,
    unique_title_percentage,
    story_percentage,
    example_title,
    example_url,
    example_source,
    first_occurrence_date,
    last_occurrence_date
from ranked_topics
where topic_rank <= 20
