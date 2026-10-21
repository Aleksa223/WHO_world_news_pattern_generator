with word_occurrences as (
    select
        article_id,
        category,
        content_type,
        title_word,
        title,
        normalized_title,
        url,
        observation_date,
        observed_at,
        feed_rank
    from {{ ref('who_int_title_topics') }}
),

ranked_examples as (
    select
        *,
        row_number() over (
            partition by category, title_word
            order by
                observed_at desc,
                feed_rank,
                title,
                article_id
        ) as example_rank
    from word_occurrences
),

word_counts as (
    select
        category,
        title_word,
        max(case when example_rank = 1 then title end) as example_title,
        max(case when example_rank = 1 then url end) as example_url,
        count(distinct article_id) as content_count,
        count(distinct normalized_title) as unique_title_count,
        min(observation_date) as first_occurrence_date,
        max(observation_date) as last_occurrence_date
    from ranked_examples
    group by
        category,
        title_word
),

corpus_totals as (
    select
        content_type as category,
        count(*) as corpus_content_count,
        count(distinct lower(trim(title))) as corpus_unique_title_count
    from {{ ref('who_int_content') }}
    group by content_type
),

ranked_words as (
    select
        word_counts.*,
        corpus_totals.corpus_content_count,
        corpus_totals.corpus_unique_title_count,
        round(
            100.0 * word_counts.unique_title_count
                / nullif(corpus_totals.corpus_unique_title_count, 0),
            2
        ) as unique_title_percentage,
        round(
            100.0 * word_counts.content_count
                / nullif(corpus_totals.corpus_content_count, 0),
            2
        ) as content_percentage,
        row_number() over (
            partition by word_counts.category
            order by
                word_counts.unique_title_count desc,
                word_counts.content_count desc,
                word_counts.title_word
        ) as word_rank
    from word_counts
    inner join corpus_totals
        on word_counts.category = corpus_totals.category
)

select
    category || ':' || title_word as word_key,
    category,
    category as content_type,
    word_rank,
    title_word,
    unique_title_count,
    content_count,
    corpus_unique_title_count,
    corpus_content_count,
    unique_title_percentage,
    content_percentage,
    example_title,
    example_url,
    first_occurrence_date,
    last_occurrence_date
from ranked_words
where word_rank <= 20
