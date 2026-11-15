-- migration: 0000073
-- requires: 0000072

alter table fiskaly_provisioning_job drop constraint fiskaly_provisioning_job_tse_id_key;
alter table fiskaly_provisioning_job drop constraint fiskaly_provisioning_job_event_node_id_key;
alter table fiskaly_provisioning_job add column scope_node_id bigint references node(id);
update fiskaly_provisioning_job set scope_node_id=event_node_id;
alter table fiskaly_provisioning_job alter column scope_node_id set not null;
alter table fiskaly_provisioning_job add unique (scope_node_id);

create function fiskaly_scope_immutable() returns trigger as $$
begin
    if NEW.scope_node_id is distinct from OLD.scope_node_id then
        raise exception 'Persisted Fiskaly deployment scope is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_scope_immutable before update on fiskaly_provisioning_job
    for each row execute function fiskaly_scope_immutable();

create table fiskaly_client (
    id uuid primary key,
    tse_id bigint not null references tse(id),
    serial text not null,
    registered boolean not null default false,
    unique (tse_id, serial),
    unique (tse_id, id)
);

insert into fiskaly_client(id,tse_id,serial,registered)
select client_id,tse_id,till_id::text,registered from fiskaly_client_binding;

alter table fiskaly_client_binding drop constraint fiskaly_client_binding_client_id_key;
alter table fiskaly_client_binding add foreign key (tse_id,client_id) references fiskaly_client(tse_id,id);
create index fiskaly_client_binding_client on fiskaly_client_binding(client_id);

alter table fiskaly_provisioning_job add column paused boolean not null default false;

create view fiskaly_managed_till as
select t.id as till_id, j.tse_id, j.id as job_id,
       not (j.paused or scope.read_only or n.read_only or customer.read_only) as active
from till t
join node n on n.id=t.node_id
join fiskaly_provisioning_job j on j.scope_node_id=any(n.parents_until_event_node || n.id)
join node scope on scope.id=j.scope_node_id
join fiskaly_site s on s.id=j.site_id
join node customer on customer.id=s.customer_node_id
where customer.id=any(scope.parent_ids || scope.id)
  and (t.tse_id is null or t.tse_id=j.tse_id);


create function fiskaly_client_identity_immutable() returns trigger as $$
begin
    if (NEW.id, NEW.tse_id, NEW.serial) is distinct from (OLD.id, OLD.tse_id, OLD.serial) then
        raise exception 'Persisted Fiskaly client identity is immutable';
    end if;
    return NEW;
end;
$$ language plpgsql;
create trigger fiskaly_client_identity_immutable before update on fiskaly_client
    for each row execute function fiskaly_client_identity_immutable();

alter table tse_signature add column fiskaly_site_id bigint references fiskaly_site(id);
update tse_signature sig set fiskaly_site_id=j.site_id
from tse t join fiskaly_provisioning_job j on j.id=t.fiskaly_job_id
where sig.tse_id=t.id;

update tse_signature sig set fiskaly_site_id=j.site_id
from ordr o join fiskaly_managed_till m on m.till_id=o.till_id
join fiskaly_provisioning_job j on j.id=m.job_id
where sig.id=o.id and sig.tse_id is null and j.tse_id is not null;

create table fiskaly_till_outage (
    id bigint generated always as identity primary key,
    till_id bigint not null references till(id),
    tse_id bigint not null references tse(id),
    started_at timestamptz not null default clock_timestamp(),
    ended_at timestamptz,
    reason text not null
);
create unique index fiskaly_till_open_outage on fiskaly_till_outage(till_id,tse_id) where ended_at is null;

alter table tse_signature add column fiskaly_start_attempted boolean not null default false;
update tse_signature set fiskaly_start_attempted=true
where fiskaly_transaction_id is not null and fiskaly_attempts>0;
