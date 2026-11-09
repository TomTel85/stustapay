-- migration: 0000067
-- requires: 0000066

create table terminal_payout_journal (
    uuid uuid primary key,
    terminal_id bigint not null,
    till_id bigint not null,
    request jsonb not null,
    result jsonb not null
);

alter table pending_sumup_order add column terminal_id bigint;
