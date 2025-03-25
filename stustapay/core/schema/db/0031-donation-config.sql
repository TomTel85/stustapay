-- migration: 9999996
-- requires: 9999997

alter table event add column donation_enabled boolean default true not null; 