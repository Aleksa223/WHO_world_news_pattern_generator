with stories as (
    select
        coalesce(
            date(published_at),
            date(first_seen_at)
        ) as publication_date,
        coalesce(nullif(trim(feed), ''), 'unknown') as feed,
        coalesce(nullif(trim(category), ''), 'uncategorized') as category,
        coalesce(score, 0) as score,
        coalesce(comment_count, 0) as comment_count,
        published_at
    from {{ ref('tech_stg_story') }}
)

select
    publication_date || ':' || feed || ':' || category as summary_key,
    publication_date,
    feed,
    category,
    count(*) as story_count,
    sum(score) as total_score,
    round(avg(score), 2) as average_score,
    sum(comment_count) as total_comments,
    round(avg(comment_count), 2) as average_comments,
    min(published_at) as first_published_at,
    max(published_at) as last_published_at
from stories
group by
    publication_date,
    feed,
    category
