-- migration: 0000059
-- requires: 0000058

-- Earlier branch upgrades from a6f94d21 could skip the payment migrations
-- because they were inserted before that released revision. Repair those
-- databases as well as databases created with the corrected migration chain.
alter table event
    add column if not exists customer_portal_font_color text default null,
    add column if not exists tap_to_pay_enabled boolean not null default false;
alter table till_profile
    add column if not exists tap_to_pay_enabled boolean not null default false;

do $$
begin
    if exists (select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'terminal' and column_name = 'tap_to_pay_enabled') then
        update till_profile as profile
        set tap_to_pay_enabled = true
        where exists (
            select 1 from till join terminal on terminal.id = till.terminal_id
            where till.active_profile_id = profile.id and terminal.tap_to_pay_enabled
        );
        alter table terminal drop column tap_to_pay_enabled;
    end if;

    if not exists (select 1 from pg_type where typname = 'sumup_environment' and typnamespace = 'public'::regnamespace) then
        create type sumup_environment as enum ('live', 'sandbox');
    end if;
    if not exists (select 1 from pg_type where typname = 'sumup_auth_method' and typnamespace = 'public'::regnamespace) then
        create type sumup_auth_method as enum ('oauth', 'api_key');
    end if;
end;
$$;

alter table event
    add column if not exists sumup_environment sumup_environment not null default 'live';
alter table pending_sumup_order
    add column if not exists sumup_environment sumup_environment not null default 'live';
alter table node_sumup_link
    add column if not exists environment sumup_environment not null default 'live',
    add column if not exists auth_method sumup_auth_method not null default 'oauth',
    add column if not exists api_key text,
    alter column refresh_token drop not null;
alter table node_sumup_link
    drop constraint node_sumup_link_pkey,
    add primary key (node_id, environment);

do $$
begin
    if not exists (select 1 from pg_constraint
                   where conrelid = 'node_sumup_link'::regclass and conname = 'node_sumup_link_auth_method_check') then
        alter table node_sumup_link add constraint node_sumup_link_auth_method_check check (
            (auth_method = 'oauth' and refresh_token is not null and api_key is null)
            or (auth_method = 'api_key' and api_key is not null and refresh_token is null)
        );
    end if;
end;
$$;
