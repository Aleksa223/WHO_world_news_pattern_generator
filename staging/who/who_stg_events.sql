{{ config(materialized='table') }}

select
    id,
    title,
    event_type as news_type,
    case
        when substr(id, 1, 10) glob
            '[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]'
        then date(replace(substr(id, 1, 10), '/', '-'))
        else null
    end as published_at,
    date_text as formatted_date,
    url,
    first_seen_at,
    last_seen_at
from {{ source('event_news', 'articles') }}
where lower(coalesce(event_type, '')) like '%events%'
