with history as (
    select
        'tech' as source_name,
        cast(id as text) as record_id,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('tech_article_history') }}

    union all

    select
        'economic' as source_name,
        cast(id as text) as record_id,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('economic_article_history') }}
),

invalid_intervals as (
    select
        source_name,
        record_id,
        'invalid_interval' as issue
    from history
    where datetime(dbt_valid_from) is null
       or (
            dbt_valid_to is not null
            and (
                datetime(dbt_valid_to) is null
                or julianday(dbt_valid_to) < julianday(dbt_valid_from)
            )
       )
),

duplicate_current_versions as (
    select
        source_name,
        record_id,
        'multiple_current_versions' as issue
    from history
    group by source_name, record_id
    having sum(case when dbt_valid_to is null then 1 else 0 end) > 1
)

select * from invalid_intervals
union all
select * from duplicate_current_versions
