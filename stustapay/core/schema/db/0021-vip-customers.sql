-- migration: 9999998
-- requires: 9999999

-- Add is_vip flag to user_tag table
ALTER TABLE user_tag ADD COLUMN is_vip BOOLEAN NOT NULL DEFAULT FALSE;

-- Add vip_max_account_balance to event table
ALTER TABLE event ADD COLUMN vip_max_account_balance NUMERIC NOT NULL DEFAULT 300;

