-- migration: 0000070
-- requires: 0000069

alter type tse_type add value if not exists 'fiskaly';
alter table tse add column fiskaly_profile text;
alter table tse add column last_error text;
create unique index tse_fiskaly_profile_unique on tse(fiskaly_profile) where fiskaly_profile is not null;

alter table tse_signature
    add column fiskaly_transaction_id uuid,
    add column fiskaly_client_id uuid,
    add column fiskaly_request jsonb,
    add column fiskaly_attempts integer not null default 0,
    add column fiskaly_next_attempt timestamptz not null default now(),
    add column fiskaly_last_error text;
create unique index tse_signature_fiskaly_transaction_unique on tse_signature(fiskaly_transaction_id)
    where fiskaly_transaction_id is not null;
create index tse_signature_fiskaly_retry on tse_signature(tse_id, fiskaly_next_attempt, id)
    where signature_status = 'pending' and fiskaly_transaction_id is not null;
