create view till_with_cash_register as
    select
        t.*,
        tse.serial,
        cr.name   as current_cash_register_name,
        a.balance as current_cash_register_balance
    from
        till t
        left join usr u on t.active_user_id = u.id
        left join account a on u.cashier_account_id = a.id
        left join cash_register cr on t.active_cash_register_id = cr.id
        left join tse on tse.id = t.tse_id;

create view cash_register_with_cashier as
    select
        c.*,
        t.id                   as current_till_id,
        u.id                   as current_cashier_id,
        u.user_tag_uid         as current_cashier_tag_uid,
        coalesce(a.balance, 0) as current_balance
    from
        cash_register c
        left join usr u on u.cash_register_id = c.id
        left join account a on a.id = u.cashier_account_id
        left join till t on t.active_cash_register_id = c.id;

create view user_role_with_privileges as
    select
        r.*,
        coalesce(privs.privileges, '{}'::text array) as privileges
    from
        user_role r
        left join (
            select ur.role_id, array_agg(ur.privilege) as privileges from user_role_to_privilege ur group by ur.role_id
        ) privs on r.id = privs.role_id;

create view user_with_roles as
    select
        usr.*,
        coalesce(roles.roles, '{}'::text array) as role_names
    from
        usr
        left join (
            select
                utr.user_id        as user_id,
                array_agg(ur.name) as roles
            from
                user_to_role utr
                join user_role ur on utr.role_id = ur.id
            group by utr.user_id
        ) roles on usr.id = roles.user_id;

create view user_with_privileges as
    select
        usr.*,
        coalesce(privs.privileges, '{}'::text array) as privileges
    from
        usr
        left join (
            select
                utr.user_id,
                array_agg(urtp.privilege) as privileges
            from
                user_to_role utr
                join user_role_to_privilege urtp on utr.role_id = urtp.role_id
            group by utr.user_id
        ) privs on usr.id = privs.user_id;

create view account_with_history as
    select
        a.*,
        ut.comment                             as user_tag_comment,
        ut.restriction,
        coalesce(hist.tag_history, '[]'::json) as tag_history
    from
        account a
        left join user_tag ut on a.user_tag_uid = ut.uid
        left join (
            select
                atah.account_id,
                json_agg(json_build_object('account_id', atah.account_id, 'user_tag_uid', atah.user_tag_uid,
                                           'mapping_was_valid_until', atah.mapping_was_valid_until, 'comment',
                                           ut.comment)) as tag_history
            from
                account_tag_association_history atah
                join user_tag ut on atah.user_tag_uid = ut.uid
            group by atah.account_id
                  ) hist on a.id = hist.account_id;

-- aggregates account and customer_info to customer
create view customer as
    select
        a.*,
        customer_info.*
    from
        account_with_history a
        left join customer_info on (a.id = customer_info.customer_account_id)
    where
        a.type = 'private';

create view payout as
    select
        c.node_id,
        c.customer_account_id,
        c.iban,
        c.account_name,
        c.email,
        c.user_tag_uid,
        (c.balance - c.donation) as balance,
        c.payout_run_id
    from
        customer c
    where
        c.iban is not null
        and round(c.balance, 2) > 0
        and round(c.balance - c.donation, 2) > 0
        and c.payout_export
        and c.payout_error is null;

create view payout_run_with_stats as
    select
        p.*,
        s.total_donation_amount,
        s.total_payout_amount,
        s.n_payouts
    from
        payout_run p
        join (
            select
                py.id                                                      as id,
                coalesce(sum(c.donation), 0)                               as total_donation_amount,
                coalesce(sum(c.balance), 0) - coalesce(sum(c.donation), 0) as total_payout_amount,
                count(*)                                                   as n_payouts
            from
                payout_run py
                left join customer c on py.id = c.payout_run_id
            group by py.id
             ) s on p.id = s.id;

create view user_tag_with_history as
    select
        ut.node_id,
        ut.uid                                     as user_tag_uid,
        ut.comment,
        a.id                                       as account_id,
        coalesce(hist.account_history, '[]'::json) as account_history
    from
        user_tag ut
        left join account a on a.user_tag_uid = ut.uid
        left join (
            select
                atah.user_tag_uid,
                json_agg(json_build_object('account_id', atah.account_id, 'mapping_was_valid_until',
                                           atah.mapping_was_valid_until, 'comment', ut.comment)) as account_history
            from
                account_tag_association_history atah
                join user_tag ut on atah.user_tag_uid = ut.uid
            group by atah.user_tag_uid
                  ) hist on ut.uid = hist.user_tag_uid;

create view cashier as
    select
        usr.node_id,
        usr.id,
        usr.login,
        usr.display_name,
        usr.description,
        usr.user_tag_uid,
        usr.transport_account_id,
        usr.cashier_account_id,
        usr.cash_register_id,
        a.balance                                    as cash_drawer_balance,
        coalesce(tills.till_ids, '{}'::bigint array) as till_ids
    from
        usr
        join account a on usr.cashier_account_id = a.id
        left join (
            select
                t.active_user_id as user_id,
                array_agg(t.id)  as till_ids
            from
                till t
            where
                t.active_user_id is not null
            group by t.active_user_id
                  ) tills on tills.user_id = usr.id;

create view product_with_tax_and_restrictions as
    select
        p.*,
        -- price_in_vouchers is never 0 due to constraint product_price_in_vouchers_not_zero
        p.price / p.price_in_vouchers               as price_per_voucher,
        t.name                                      as tax_name,
        t.rate                                      as tax_rate,
        coalesce(pr.restrictions, '{}'::text array) as restrictions
    from
        product p
        join tax_rate t on p.tax_rate_id = t.id
        left join (
            select r.id, array_agg(r.restriction) as restrictions from product_restriction r group by r.id
        ) pr on pr.id = p.id;

create view ticket as
    select
        p.*,
        ptm.initial_top_up_amount,
        ptm.initial_top_up_amount + p.price as total_price
    from
        product_with_tax_and_restrictions p
        join product_ticket_metadata ptm on p.ticket_metadata_id = ptm.id;

create view till_button_with_products as
    select
        t.id,
        t.name,
        t.node_id,
        coalesce(j_view.price, 0)                        as price, -- sane defaults for buttons without a product
        coalesce(j_view.price_in_vouchers, 0)            as price_in_vouchers,
        coalesce(j_view.price_per_voucher, 0)            as price_per_voucher,
        coalesce(j_view.fixed_price, true)               as fixed_price,
        coalesce(j_view.is_returnable, false)            as is_returnable,
        coalesce(j_view.product_ids, '{}'::bigint array) as product_ids
    from
        till_button t
        left join (
            select
                tlb.button_id,
                sum(coalesce(p.price, 0))             as price,

                -- this assumes that only one product can have a voucher value
                -- because we'd need the products individual voucher prices
                -- and start applying vouchers to the highest price_per_voucher product first.
                sum(coalesce(p.price_in_vouchers, 0)) as price_in_vouchers,
                sum(coalesce(p.price_per_voucher, 0)) as price_per_voucher,

                bool_and(p.fixed_price)               as fixed_price,   -- a constraint assures us that for variable priced products a button can only refer to one product
                bool_and(p.is_returnable)             as is_returnable, -- a constraint assures us that for returnable products a button can only refer to one product
                array_agg(tlb.product_id)             as product_ids
            from
                till_button_product tlb
                join product_with_tax_and_restrictions p on tlb.product_id = p.id
            group by tlb.button_id
            window button_window as (partition by tlb.button_id)
                  ) j_view on t.id = j_view.button_id;

create view till_layout_with_buttons_and_tickets as
    select
        t.*,
        coalesce(j_view.button_ids, '{}'::bigint array) as button_ids,
        coalesce(t_view.ticket_ids, '{}'::bigint array) as ticket_ids
    from
        till_layout t
        left join (
            select
                tltb.layout_id,
                array_agg(tltb.button_id order by tltb.sequence_number) as button_ids
            from
                till_layout_to_button tltb
            group by tltb.layout_id
                  ) j_view on t.id = j_view.layout_id
        left join (
            select
                tltt.layout_id,
                array_agg(tltt.ticket_id order by tltt.sequence_number) as ticket_ids
            from
                till_layout_to_ticket tltt
            group by tltt.layout_id
                  ) t_view on t.id = t_view.layout_id;

create view line_item_aggregated_json as
    with line_item_json as (
        select
            l.*,
            row_to_json(p) as product
        from
            line_item as l
            join product_with_tax_and_restrictions p on l.product_id = p.id
    )
    select
        order_id,
        sum(total_price)                                       as total_price,
        sum(total_tax)                                         as total_tax,
        sum(total_price - total_tax)                           as total_no_tax,
        coalesce(json_agg(line_item_json), json_build_array()) as line_items
    from
        line_item_json
    group by
        order_id;

create view order_value as
    select
        ordr.*,
        a.user_tag_uid                              as customer_tag_uid,
        coalesce(li.total_price, 0)                 as total_price,
        coalesce(li.total_tax, 0)                   as total_tax,
        coalesce(li.total_no_tax, 0)                as total_no_tax,
        coalesce(li.line_items, json_build_array()) as line_items
    from
        ordr
        left join line_item_aggregated_json li on ordr.id = li.order_id
        left join account a on ordr.customer_account_id = a.id;

-- show all line items
create view order_items as
    select
        ordr.*,
        line_item.*
    from
        ordr
        left join line_item on (ordr.id = line_item.order_id);

-- aggregated tax rate of items
create view order_tax_rates as
    select
        ordr.*,
        tax_name,
        tax_rate,
        sum(total_price)             as total_price,
        sum(total_tax)               as total_tax,
        sum(total_price - total_tax) as total_no_tax
    from
        ordr
        left join line_item on (ordr.id = order_id)
    group by
        ordr.id, tax_rate, tax_name;

create view order_value_with_bon as
    select
        o.*,
        b.generated   as bon_generated
    from
        order_value o
        left join bon b on (o.id = b.id);

create view event_with_translations as
    select
        e.*,
        '{}'::json as translations_texts,
        (
            select array_agg(language.code)
            from language
        ) as languages
    from event e;

create view _forbidden_at_node as
    with forbidden_at_node_as_list as (
        select node_id, array_agg(object_name)::varchar(255) array as object_names
        from forbidden_objects_at_node
        group by node_id
    ), forbidden_in_tree_as_list as (
        select node_id, array_agg(object_name)::varchar(255) array as object_names
        from forbidden_objects_in_subtree_at_node
        group by node_id
    )
    select
        n.id as node_id,
        coalesce(obj_at.object_names, '{}'::varchar(255) array) as forbidden_objects_at_node,
        coalesce(obj_tree.object_names, '{}'::varchar(255) array) as forbidden_objects_in_subtree
    from node n
    left join forbidden_at_node_as_list obj_at on n.id = obj_at.node_id
    left join forbidden_in_tree_as_list obj_tree on n.id = obj_tree.node_id;

create view _forbidden_at_node_computed as
    with recursive graph (
        node_id, depth, path, cycle, computed_forbidden_at_node, computed_forbidden_in_subtree, forbidden_at_node,
        forbidden_in_subtree
    ) as (
        -- base case: start at the requested node
        select
            0::bigint, -- root node ID
            1,
            '{0}'::bigint[],
            false,
            '{}'::varchar(255) array,
            '{}'::varchar(255) array,
            '{}'::varchar(255) array,
            '{}'::varchar(255) array
        union all
        -- add the node's children result set (find the parents for all so-far evaluated nodes)
        select
            node.id,
            g.depth + 1,
            g.path || node.parent,
            node.id = any(g.path),
            (g.computed_forbidden_in_subtree || fan.forbidden_objects_at_node)::varchar(255) array,
            (g.computed_forbidden_in_subtree || fan.forbidden_objects_in_subtree)::varchar(255) array,
            fan.forbidden_objects_at_node,
            fan.forbidden_objects_in_subtree
        from
            graph g
            join node on g.node_id = node.parent
            join _forbidden_at_node fan ON node.id = fan.node_id
        where
            node.id != 0
            and not g.cycle
    )
    select
        g.node_id,
        g.computed_forbidden_in_subtree,
        g.computed_forbidden_at_node,
        g.forbidden_in_subtree,
        g.forbidden_at_node
    from graph g;

-- TODO: this view will be monstrous, as it needs to do the transitive calculation of allowed objects at a tree
create view node_with_allowed_objects as
    with event_as_json as (
        select id, row_to_json(event_with_translations) as json_row
        from event_with_translations
    )
    select
        n.*,
        fan.forbidden_at_node as forbidden_objects_at_node,
        case
            when n.event_node_id is null then -- nodes above event nodes
                fan.computed_forbidden_at_node || '{"ticket", "product", "tax_rate", "till", "user_tag", "account", "terminal"}'::varchar(255) array
            when n.event_node_id is not null and n.event_node_id != n.id then -- nodes blow event node
                fan.computed_forbidden_at_node || '{"user_role", "user_tag", "account", "tse", "tax_rate"}'::varchar(255) array
            else
                fan.computed_forbidden_at_node
        end as computed_forbidden_objects_at_node,
        fan.forbidden_in_subtree as forbidden_objects_in_subtree,
        fan.computed_forbidden_in_subtree as computed_forbidden_objects_in_subtree,
        ev.json_row as event
    from node n
    join _forbidden_at_node_computed fan on n.id = fan.node_id
    left join event_as_json ev on n.event_id = ev.id