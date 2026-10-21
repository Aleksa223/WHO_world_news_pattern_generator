with expected as (
    select 'who:' || content_key as article_key
    from {{ ref('who_int_content') }}

    union all

    select 'tech:' || cast(id as text) as article_key
    from {{ ref('tech_stg_story') }}

    union all

    select 'economic:' || cast(id as text) as article_key
    from {{ ref('economic_stg_articles') }}
),

actual as (
    select article_key
    from {{ ref('all_news_mart_articles') }}
),

missing_from_mart as (
    select expected.article_key
    from expected
    left join actual using (article_key)
    where actual.article_key is null
),

unexpected_in_mart as (
    select actual.article_key
    from actual
    left join expected using (article_key)
    where expected.article_key is null
)

select article_key, 'missing_from_mart' as coverage_error
from missing_from_mart
union all
select article_key, 'unexpected_in_mart' as coverage_error
from unexpected_in_mart
