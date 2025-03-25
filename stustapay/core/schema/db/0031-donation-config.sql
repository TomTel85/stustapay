-- migration: donation_enabled
-- requires: 2b0f2fb3

alter table event add column donation_enabled boolean default true not null; 