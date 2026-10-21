with expected_counts as (
    select
        category,
        canonical_topic as topic,
        count(distinct article_id) as story_count,
        count(distinct normalized_title) as unique_title_count
    from {{ ref('tech_int_title_topics') }}
    group by
        category,
        canonical_topic
)

select
    mart.topic_key,
    mart.story_count as actual_story_count,
    expected_counts.story_count as expected_story_count,
    mart.unique_title_count as actual_unique_title_count,
    expected_counts.unique_title_count as expected_unique_title_count
from {{ ref('tech_mart_top_title_topics') }} as mart
inner join expected_counts
    on mart.category = expected_counts.category
   and mart.topic = expected_counts.topic
where mart.story_count <> expected_counts.story_count
   or mart.unique_title_count <> expected_counts.unique_title_count
