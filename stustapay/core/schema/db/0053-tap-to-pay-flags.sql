-- migration: 92f445c4
-- requires: 13c7b823

alter table event add column if not exists tap_to_pay_enabled boolean not null default false;

alter table terminal add column if not exists tap_to_pay_enabled boolean not null default false;

create or replace view event_with_translations as
    select
        e.*,
        '{}'::json as translations_texts,
        (
            select array_agg(language.code)
            from language
        ) as languages
    from event e;
