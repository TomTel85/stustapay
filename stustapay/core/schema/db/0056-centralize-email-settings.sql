-- migration: 0000056
-- requires: 9d5f7c31

alter table event rename column email_enabled to payout_email_enabled;

alter table event add column email_use_global_settings boolean not null default true;

-- Preserve complete, enabled event-local SMTP configurations. Other events either
-- had mail disabled or incomplete settings and should use the global fallback.
update event
set email_use_global_settings = false
where payout_email_enabled
  and email_default_sender is not null
  and email_smtp_host is not null
  and email_smtp_port is not null;
