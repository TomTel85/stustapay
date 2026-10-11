-- migration: 0000063
-- requires: 0000062

-- Normalize existing catalog prices without changing historical line items.
update product set price = round(price, 2) where price != round(price, 2);

-- Cover every writer, including imports, event copies, and direct SQL updates.
create function normalize_product_price() returns trigger as $$
begin
    new.price := round(new.price, 2);
    return new;
end;
$$ language plpgsql;

create trigger normalize_product_price
    before insert or update of price on product
    for each row execute function normalize_product_price();

alter table product add constraint product_price_cent_precision check (
    price is null or (
        price not in ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)
        and price = round(price, 2)
    )
);
