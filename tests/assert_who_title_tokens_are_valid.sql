select *
from {{ ref('who_int_title_topics') }}
where title_word = ''
   or title_word glob '*[0-9]*'
   or title_word glob '*[^a-z0-9]*'
   or (
       length(title_word) < 4
       and is_mapped = 0
   )
   or topic <> title_word
