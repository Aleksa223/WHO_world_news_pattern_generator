with expected_current_ids as (
    select
        'tech' as source_name,
        cast(id as text) as record_id
    from {{ source('tech_news', 'tech_articles') }}

    union all

    select
        'economic' as source_name,
        cast(id as text) as record_id
    from {{ source('economic_news', 'economic_articles') }}
),

actual_current_ids as (
    select
        'tech' as source_name,
        cast(id as text) as record_id
    from {{ ref('tech_article_history') }}
    where dbt_valid_to is null

    union all

    select
        'economic' as source_name,
        cast(id as text) as record_id
    from {{ ref('economic_article_history') }}
    where dbt_valid_to is null
),

missing_from_snapshot as (
    select
        expected.source_name,
        expected.record_id,
        'missing_from_snapshot' as issue
    from expected_current_ids as expected
    left join actual_current_ids as actual
        on expected.source_name = actual.source_name
       and expected.record_id = actual.record_id
    where actual.record_id is null
),

missing_from_source as (
    select
        actual.source_name,
        actual.record_id,
        'missing_from_source' as issue
    from actual_current_ids as actual
    left join expected_current_ids as expected
        on actual.source_name = expected.source_name
       and actual.record_id = expected.record_id
    where expected.record_id is null
)

select * from missing_from_snapshot
union all
select * from missing_from_source
