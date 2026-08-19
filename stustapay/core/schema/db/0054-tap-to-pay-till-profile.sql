-- migration: d4a7c9e1
-- requires: 92f445c4

alter table till_profile
    add column if not exists tap_to_pay_enabled boolean not null default false;

-- Preserve existing opt-ins while moving ownership from individual terminals
-- to the profile shared by their active till.
update till_profile as profile
set tap_to_pay_enabled = true
where exists (
    select 1
    from till
    join terminal on terminal.id = till.terminal_id
    where till.active_profile_id = profile.id
      and terminal.tap_to_pay_enabled
);

alter table terminal drop column if exists tap_to_pay_enabled;
