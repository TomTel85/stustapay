-- migration: 0000062
-- requires: 0000061

alter table terminal_offline_import
    add column attempt_count integer not null default 1,
    add column last_attempt_at timestamptz not null default now();

alter table terminal_offline_rejection
    add column attempt_count integer not null default 1,
    add column last_attempt_at timestamptz not null default now();

-- Re-evaluate old failures once under the improved reconciliation rules. Invalid inputs remain visible.
update terminal_offline_import set result=jsonb_set(result, '{status}', '"retry_required"')
    where resolved_at is null and result->>'status'='clarification_required';

create index terminal_offline_import_snapshot_sequence on terminal_offline_import(snapshot_id, sequence);
create index terminal_offline_import_retry on terminal_offline_import(last_attempt_at)
    where resolved_at is null and result->>'status' in ('retry_required','clarification_required');
create index terminal_offline_rejection_retry on terminal_offline_rejection(last_attempt_at)
    where resolved_at is null;
