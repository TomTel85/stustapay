-- migration: 0000066
-- requires: 0000065

create table usr_mfa (
    usr bigint primary key references usr(id) on delete cascade,
    secret bytea,
    pending_secret bytea,
    pending_since timestamptz,
    last_step bigint not null default -1,
    recovery_hashes text[] not null default '{}',
    attempts integer not null default 0,
    attempt_window timestamptz not null default now()
);
