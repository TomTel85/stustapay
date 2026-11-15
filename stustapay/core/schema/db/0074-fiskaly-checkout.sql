-- migration: 0000074
-- requires: 0000073

create table fiskaly_checkout (
    sale_uuid uuid primary key,
    till_id bigint not null references till(id),
    terminal_id bigint not null references terminal(id),
    tse_id bigint not null references tse(id),
    client_id uuid not null references fiskaly_client(id),
    transaction_id uuid not null unique,
    created_at timestamptz not null default clock_timestamp(),
    start_attempted_at timestamptz,
    started_at timestamptz,
    finished boolean not null default false,
    abort_requested boolean not null default false,
    next_attempt timestamptz not null default now(),
    last_error text
);

create index fiskaly_checkout_due on fiskaly_checkout(tse_id,next_attempt) where not finished;

alter table tse_signature add column fiskaly_checkout boolean not null default false;
