-- migration: 9999997
-- requires: 9999998

alter table mails add column if not exists retry_count int not null default 0;
alter table mails add column if not exists retry_max int not null default 5;
alter table mails add column if not exists retry_next_attempt timestamp;
alter table mails add column if not exists failure_reason text; 