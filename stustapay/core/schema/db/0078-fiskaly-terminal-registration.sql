-- migration: 0000078
-- requires: 0000077

create or replace view fiskaly_managed_till as
select t.id as till_id, j.tse_id, j.id as job_id,
       not (j.paused or event_node.read_only or scope.read_only or n.read_only or customer.read_only
            or coalesce(e.end_date <= now(), false))
       and t.terminal_id is not null as active,
       coalesce(e.end_date + interval '47 hours' <= now(), false) as deregistration_due
from till t
join node n on n.id=t.node_id
join fiskaly_provisioning_job j on j.scope_node_id=any(n.parents_until_event_node || n.id)
join node scope on scope.id=j.scope_node_id
join fiskaly_site s on s.id=j.site_id
join node customer on customer.id=s.customer_node_id
join node event_node on event_node.id=j.event_node_id
join event e on e.id=event_node.event_id
where customer.id=any(scope.parent_ids || scope.id)
  and (t.tse_id is null or t.tse_id=j.tse_id);
