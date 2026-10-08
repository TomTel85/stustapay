-- migration: 0000061
-- requires: 0000060

alter table event
    add column if not exists offline_enabled boolean not null default false,
    add column if not exists offline_validity_seconds integer not null default 7200 check (offline_validity_seconds between 60 and 86400),
    add column if not exists offline_sale_per_transaction_cents bigint not null default 2000 check (offline_sale_per_transaction_cents >= 0),
    add column if not exists offline_sale_per_customer_cents bigint not null default 3000 check (offline_sale_per_customer_cents >= 0),
    add column if not exists offline_sale_per_till_cents bigint not null default 50000 check (offline_sale_per_till_cents >= 0),
    add column if not exists offline_return_per_transaction_cents bigint not null default 2000 check (offline_return_per_transaction_cents >= 0),
    add column if not exists offline_return_per_customer_cents bigint not null default 3000 check (offline_return_per_customer_cents >= 0),
    add column if not exists offline_return_per_till_cents bigint not null default 50000 check (offline_return_per_till_cents >= 0);

-- Offline operation must stay disabled for every existing event during rollout and pilot.
update event set offline_enabled = false;

-- Historical terminal IDs intentionally have no FK: deleting a retired device must preserve its audit trail.
create table terminal_offline_snapshot (
    id uuid primary key,
    terminal_id bigint not null,
    session_uuid uuid not null,
    event_node_id bigint not null references node(id),
    till_id bigint not null references till(id),
    user_id bigint not null references usr(id),
    prepared_at timestamptz not null,
    valid_until timestamptz not null,
    last_contact_at timestamptz not null,
    snapshot jsonb not null,
    till_config jsonb not null,
    cash_register_id bigint,
    check (valid_until > prepared_at)
);
create index terminal_offline_snapshot_terminal on terminal_offline_snapshot(terminal_id, prepared_at desc);

-- Stores the exact original input and result, including online sales.
create table terminal_sale_journal (
    uuid uuid primary key,
    terminal_id bigint not null,
    request jsonb not null,
    result jsonb not null
);

create table terminal_offline_import (
    uuid uuid primary key,
    snapshot_id uuid not null references terminal_offline_snapshot(id),
    sequence bigint not null check (sequence > 0),
    request jsonb not null,
    result jsonb not null,
    received_at timestamptz not null default now(),
    resolved_at timestamptz,
    resolved_by bigint references usr(id)
);


-- Invalid snapshot references and conflicting retransmissions are also retained for review.
create table terminal_offline_rejection (
    id bigint generated always as identity primary key,
    terminal_id bigint not null,
    node_id bigint not null references node(id),
    till_id bigint not null,
    user_id bigint not null,
    request jsonb not null,
    result jsonb not null,
    received_at timestamptz not null default now(),
    resolved_at timestamptz,
    resolved_by bigint references usr(id)
);
