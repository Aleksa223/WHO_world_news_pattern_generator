with scored_stories as (
    select
        id,
        coalesce(date(published_at), date(first_seen_at)) as publication_date,
        title,
        url,
        discussion_url,
        author,
        coalesce(nullif(trim(feed), ''), 'unknown') as feed,
        coalesce(nullif(trim(category), ''), 'uncategorized') as category,
        published_at,
        coalesce(score, 0) as score,
        coalesce(comment_count, 0) as comment_count,
        coalesce(score, 0) + coalesce(comment_count, 0) as engagement_score
    from {{ ref('tech_stg_story') }}
),

ranked_stories as (
    select
        *,
        row_number() over (
            partition by publication_date
            order by
                engagement_score desc,
                score desc,
                comment_count desc,
                published_at desc,
                id
        ) as story_rank
    from scored_stories
)

select
    publication_date || ':' || id as story_key,
    publication_date,
    story_rank,
    id,
    title,
    url,
    discussion_url,
    author,
    feed,
    category,
    published_at,
    score,
    comment_count,
    engagement_score
from ranked_stories
where story_rank <= 10
