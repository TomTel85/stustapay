-- migration: 0000072
-- requires: 0000071

create table fiskaly_site (
    id bigint generated always as identity primary key,
    customer_node_id bigint not null references node(id),
    identity uuid not null unique,
    name text not null,
    operator_name text not null,
    address_line1 text not null,
    zip text not null,
    town text not null,
    country_code text not null,
    vat_id text,
    organization_id uuid unique,
    group_id uuid,
    creation_started boolean not null default false
);
create table fiskaly_site_environment (
    site_id bigint not null references fiskaly_site(id),
    environment text not null check(environment in ('TEST','LIVE')),
    key_identity uuid not null unique,
    key_id uuid unique,
    credential_ciphertext text,
    creation_started boolean not null default false,
    primary key(site_id,environment)
);
create table fiskaly_provisioning_job (
    id bigint generated always as identity primary key,
    site_id bigint not null references fiskaly_site(id),
    event_node_id bigint not null unique references node(id),
    environment text not null check(environment in ('TEST','LIVE')),
    status text not null default 'queued' check(status in
        ('queued','running','ready','retry_wait','action_required','failed')),
    step text not null default 'organization',
    last_error text,
    attempts integer not null default 0,
    next_attempt_at timestamptz not null default now(),
    tse_id bigint unique references tse(id),
    pin_ciphertext text,
    replace_unfinished_key boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index fiskaly_job_due on fiskaly_provisioning_job(next_attempt_at)
    where status in ('queued','running','retry_wait');
alter table tse add column fiskaly_job_id bigint unique references fiskaly_provisioning_job(id);
create function fiskaly_site_identity_immutable() returns trigger as $$
begin
    if NEW.identity is distinct from OLD.identity or NEW.customer_node_id is distinct from OLD.customer_node_id
       or (OLD.organization_id is not null and NEW.organization_id is distinct from OLD.organization_id)
       or (OLD.group_id is not null and NEW.group_id is distinct from OLD.group_id) then
        raise exception 'Persisted Fiskaly site identity is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_site_identity_immutable before update on fiskaly_site
    for each row execute function fiskaly_site_identity_immutable();
create function fiskaly_job_identity_immutable() returns trigger as $$
begin
    if NEW.site_id is distinct from OLD.site_id or NEW.event_node_id is distinct from OLD.event_node_id
       or NEW.environment is distinct from OLD.environment
       or (OLD.tse_id is not null and NEW.tse_id is distinct from OLD.tse_id) then
        raise exception 'Persisted Fiskaly onboarding identity is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_job_identity_immutable before update on fiskaly_provisioning_job
    for each row execute function fiskaly_job_identity_immutable();

create function fiskaly_tse_job_immutable() returns trigger as $$
begin
    if OLD.fiskaly_job_id is not null and NEW.fiskaly_job_id is distinct from OLD.fiskaly_job_id then
        raise exception 'Persisted Fiskaly TSE onboarding assignment is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_tse_job_immutable before update on tse
    for each row execute function fiskaly_tse_job_immutable();
