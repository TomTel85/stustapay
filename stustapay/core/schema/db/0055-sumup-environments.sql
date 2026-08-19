-- migration: 7f3e9b21
-- requires: d4a7c9e1

create type sumup_environment as enum ('live', 'sandbox');
create type sumup_auth_method as enum ('oauth', 'api_key');

-- Both views expose event columns through e.*. Drop them before appending the
-- new event column so PostgreSQL does not interpret the shifted synthetic
-- columns as a rename. The canonical db_code views are recreated afterwards.
drop view if exists node_with_allowed_objects;
drop view if exists event_with_translations;

alter table event
    add column sumup_environment sumup_environment not null default 'live';

alter table pending_sumup_order
    add column sumup_environment sumup_environment not null default 'live';

alter table node_sumup_link
    add column environment sumup_environment not null default 'live',
    add column auth_method sumup_auth_method not null default 'oauth',
    add column api_key text,
    alter column refresh_token drop not null;

alter table node_sumup_link
    drop constraint node_sumup_link_pkey,
    add primary key (node_id, environment),
    add constraint node_sumup_link_auth_method_check check (
        (auth_method = 'oauth' and refresh_token is not null and api_key is null)
        or
        (auth_method = 'api_key' and api_key is not null and refresh_token is null)
    );
