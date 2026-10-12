-- migration: 0000065
-- requires: 0000064

-- Use the oldest non-empty event text for each language unless a global value
-- already exists. Privacy policies are no longer stored on events.
insert into config (key, value, node_id)
select 'customer_portal.privacy_policy.' || languages.lang_code,
       coalesce((select content from translation_text
                 where type = 'privacy_policy' and lang_code = languages.lang_code
                   and btrim(content) != ''
                 order by event_id limit 1), ''),
       0
from (values ('de-DE'), ('en-US')) as languages(lang_code)
on conflict (key) do nothing;

delete from translation_text where type = 'privacy_policy';

alter table translation_text add constraint translation_text_no_event_privacy_policy
    check (type != 'privacy_policy');


-- Retain the legacy column for API compatibility, but no event-specific URL.
update event set customer_portal_data_privacy_url = '';
alter table event add constraint event_no_custom_privacy_url
    check (customer_portal_data_privacy_url = '');
