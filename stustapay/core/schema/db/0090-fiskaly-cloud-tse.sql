-- revision: 99999998
-- requires: c66cbafc

ALTER TYPE tse_type ADD VALUE 'fiskaly' AFTER 'diebold_nixdorf';
ALTER TABLE till ADD COLUMN fiskaly_uuid uuid UNIQUE DEFAULT gen_random_uuid();