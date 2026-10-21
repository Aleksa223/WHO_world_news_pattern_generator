select
    'word' as mart_type,
    word_key as metric_key
from {{ ref('who_mart_top_title_words') }}
where unique_title_count > corpus_unique_title_count
   or content_count > corpus_content_count
   or unique_title_percentage < 0
   or unique_title_percentage > 100
   or content_percentage < 0
   or content_percentage > 100
   or word_rank < 1
   or word_rank > 20

union all

select
    'topic' as mart_type,
    topic_key as metric_key
from {{ ref('who_mart_top_title_topics') }}
where unique_title_count > corpus_unique_title_count
   or content_count > corpus_content_count
   or unique_title_percentage < 0
   or unique_title_percentage > 100
   or content_percentage < 0
   or content_percentage > 100
   or topic_rank < 1
   or topic_rank > 20
