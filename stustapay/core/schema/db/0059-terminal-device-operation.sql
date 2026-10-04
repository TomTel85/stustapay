-- migration: 0000059
-- requires: 0000058

-- Recreated from db_code, including dependent cashier views.
drop view if exists user_with_tag cascade;
alter table usr add column is_device_identity boolean not null default false;
alter table terminal
    add column login_mode text not null default 'personal' check (login_mode in ('personal', 'device')),
    add column device_role_id bigint references user_role(id),
    add column device_user_id bigint unique references usr(id) on delete restrict,
    add constraint device_role_required check (login_mode <> 'device' or
        (device_role_id is not null and device_user_id is not null));
