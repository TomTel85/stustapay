-- migration: 0000064
-- requires: 0000063

-- Seed each language from the oldest event with a non-empty FAQ. Keep the
-- event texts so differing versions remain available for manual reconciliation.
insert into config (key, value, node_id)
select 'customer_portal.faq.' || languages.lang_code,
       coalesce((select content from translation_text
                 where type = 'faq' and lang_code = languages.lang_code
                   and btrim(content) != ''
                 order by event_id limit 1), ''),
       0
from (values ('de-DE'), ('en-US')) as languages(lang_code)
on conflict (key) do nothing;
