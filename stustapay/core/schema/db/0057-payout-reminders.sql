-- migration: 0000057
-- requires: 0000056

-- event_with_translations and node_with_allowed_objects expose event.*. Recreate
-- them from db_code after adding the new event columns.
drop view if exists node_with_allowed_objects;
drop view if exists event_with_translations;

alter table event
    add column payout_reminder_enabled boolean not null default false,
    add column payout_reminder_weekday smallint not null default 0
        check (payout_reminder_weekday between 0 and 6),
    add column payout_reminder_time time not null default time '09:00',
    add column payout_reminder_next_check_at timestamptz;

create table payout_reminder_recipient (
    event_id bigint not null references event(id) on delete cascade,
    user_id bigint not null references usr(id) on delete cascade,
    primary key (event_id, user_id)
);

create index payout_reminder_due_events_idx
    on event (payout_reminder_next_check_at)
    where payout_reminder_enabled;
