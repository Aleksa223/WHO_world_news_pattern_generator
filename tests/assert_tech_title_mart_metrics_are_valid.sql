select
    'word' as mart_type,
    word_key as metric_key
from {{ ref('tech_mart_top_title_words') }}
where unique_title_count > corpus_unique_title_count
   or story_count > corpus_story_count
   or unique_title_percentage < 0
   or unique_title_percentage > 100
   or story_percentage < 0
   or story_percentage > 100
   or word_rank < 1
   or word_rank > 20

union all

select
    'topic' as mart_type,
    topic_key as metric_key
from {{ ref('tech_mart_top_title_topics') }}
where unique_title_count > corpus_unique_title_count
   or story_count > corpus_story_count
   or unique_title_percentage < 0
   or unique_title_percentage > 100
   or story_percentage < 0
   or story_percentage > 100
   or topic_rank < 1
   or topic_rank > 20
