-- migration: 9d5f7c31
-- requires: 7f3e9b21

alter table product add column is_donation boolean not null default false;

comment on column product.is_donation is
    'whether sales of this product are reported as product donations';
