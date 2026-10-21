with topic_occurrences as (
    select
        topics.content_type,
        topics.topic,
        topics.title,
        content.published_date,
        row_number() over (
            partition by topics.content_type, topics.topic
            order by
                case when content.published_date is null then 1 else 0 end,
                content.published_date desc,
                topics.title
        ) as example_rank
    from {{ ref('who_int_title_topics') }} as topics
    inner join {{ ref('who_int_content') }} as content
        on topics.content_key = content.content_key
),

topic_counts as (
    select
        content_type,
        topic,
        max(case when example_rank = 1 then title end) as example_title,
        count(*) as title_count,
        min(published_date) as first_occurrence_date,
        max(published_date) as last_occurrence_date
    from topic_occurrences
    group by
        content_type,
        topic
),

category_totals as (
    select
        content_type,
        count(*) as category_total
    from {{ ref('who_int_content') }}
    group by content_type
),

ranked_topics as (
    select
        topic_counts.content_type,
        topic_counts.topic,
        topic_counts.example_title,
        topic_counts.title_count,
        topic_counts.first_occurrence_date,
        topic_counts.last_occurrence_date,
        category_totals.category_total,
        round(
            100.0 * topic_counts.title_count / category_totals.category_total,
            1
        ) as topic_percentage,
        row_number() over (
            partition by topic_counts.content_type
            order by
                topic_counts.title_count desc,
                topic_counts.topic
        ) as topic_rank
    from topic_counts
    inner join category_totals
        on topic_counts.content_type = category_totals.content_type
),

top_topics as (
    select *
    from ranked_topics
    where topic_rank <= 3
),

formatted_topics as (
    select
        *,
        case strftime('%m', first_occurrence_date)
            when '01' then 'Jan'
            when '02' then 'Feb'
            when '03' then 'Mar'
            when '04' then 'Apr'
            when '05' then 'May'
            when '06' then 'Jun'
            when '07' then 'Jul'
            when '08' then 'Aug'
            when '09' then 'Sep'
            when '10' then 'Oct'
            when '11' then 'Nov'
            when '12' then 'Dec'
        end
        || ' ' || cast(strftime('%d', first_occurrence_date) as integer)
        || ' ' || strftime('%Y', first_occurrence_date)
            as first_occurrence_label,
        case strftime('%m', last_occurrence_date)
            when '01' then 'Jan'
            when '02' then 'Feb'
            when '03' then 'Mar'
            when '04' then 'Apr'
            when '05' then 'May'
            when '06' then 'Jun'
            when '07' then 'Jul'
            when '08' then 'Aug'
            when '09' then 'Sep'
            when '10' then 'Oct'
            when '11' then 'Nov'
            when '12' then 'Dec'
        end
        || ' ' || cast(strftime('%d', last_occurrence_date) as integer)
        || ' ' || strftime('%Y', last_occurrence_date)
            as last_occurrence_label
    from top_topics
)

select
    content_type || ':' || topic as topic_key,
    content_type,
    topic,
    example_title,
    title_count,
    category_total,
    topic_percentage,
    topic_rank,
    first_occurrence_date,
    last_occurrence_date,
    case
        when first_occurrence_date is null then 'Unknown'
        else first_occurrence_label || ' - ' || last_occurrence_label
    end as occurrence_period
from formatted_topics
