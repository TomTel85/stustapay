-- migration: 0000069
-- requires: 0000068

alter table terminal_offline_import
    add column budget_positive numeric,
    add column budget_negative numeric,
    add constraint terminal_offline_import_budget_check check (
        (budget_positive is null and budget_negative is null) or
        (budget_positive >= 0 and budget_negative >= 0 and budget_positive is not null and budget_negative is not null)
    );
