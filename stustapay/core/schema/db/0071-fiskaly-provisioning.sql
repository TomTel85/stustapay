-- migration: 0000071
-- requires: 0000070

alter table tse add column fiskaly_tss_id uuid;
create unique index tse_fiskaly_tss_unique on tse(fiskaly_tss_id) where fiskaly_tss_id is not null;

create table fiskaly_client_binding (
    tse_id bigint not null references tse(id),
    till_id bigint not null references till(id),
    client_id uuid not null unique,
    registered boolean not null default false,
    primary key (tse_id, till_id)
);

create function fiskaly_binding_identity_immutable() returns trigger as $$
begin
    if NEW.tse_id is distinct from OLD.tse_id or NEW.till_id is distinct from OLD.till_id
       or NEW.client_id is distinct from OLD.client_id then
        raise exception 'Persisted Fiskaly client identity is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_binding_identity_immutable before update on fiskaly_client_binding
    for each row execute function fiskaly_binding_identity_immutable();

create function fiskaly_tss_identity_immutable() returns trigger as $$
begin
    if OLD.fiskaly_tss_id is not null and NEW.fiskaly_tss_id is distinct from OLD.fiskaly_tss_id then
        raise exception 'Persisted Fiskaly TSS identity is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_tss_identity_immutable before update on tse
    for each row execute function fiskaly_tss_identity_immutable();
