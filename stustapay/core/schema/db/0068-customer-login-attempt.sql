-- migration: 0000068
-- requires: 0000067

create table customer_login_attempt (
    key text primary key,
    attempts integer not null,
    window_start timestamptz not null
);
