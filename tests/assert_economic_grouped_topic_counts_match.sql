with expected_counts as (
    select
        category,
        topic,
        count(distinct article_id) as article_count,
        count(distinct normalized_title) as unique_title_count
    from {{ ref('economic_int_title_topics') }}
    group by
        category,
        topic
)

select
    mart.topic_key,
    mart.article_count as actual_article_count,
    expected_counts.article_count as expected_article_count,
    mart.unique_title_count as actual_unique_title_count,
    expected_counts.unique_title_count as expected_unique_title_count
from {{ ref('economic_mart_top_title_topics') }} as mart
inner join expected_counts
    on mart.category = expected_counts.category
   and mart.topic = expected_counts.topic
where mart.article_count <> expected_counts.article_count
   or mart.unique_title_count <> expected_counts.unique_title_count
