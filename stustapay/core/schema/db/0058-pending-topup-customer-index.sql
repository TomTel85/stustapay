-- migration: 0000058
-- requires: 0000057

create index pending_online_topup_customer_idx
    on pending_sumup_order (((order_content #>> '{}')::json ->> 'customer_account_id'), created_at desc)
    where status = 'pending'
      and order_type = 'topup'
      and cashier_id is null
      and (order_content #>> '{}')::json ->> 'payment_method' = 'sumup_online';
