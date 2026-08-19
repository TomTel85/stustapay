-- migration: a6f94d21
-- requires: 7f3e9b21

alter table event add column customer_portal_font_color text default null;
