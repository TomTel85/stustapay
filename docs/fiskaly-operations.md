# Fiskaly SIGN DE operations

The Fiskaly SIGN DE provider, durable signing worker, retry state, administration profile selection, and multi-customer onboarding workflow are implemented locally and covered by automated tests. This is not a LIVE readiness declaration: no TEST credentials were accessed, no real TEST signature was verified, and no Fiskaly resources were changed. Complete the real-cloud TEST pilot gates below before operational use.

## Configuration

This increment requires migrations `0000063`, `0000064`, and `0000065` before starting the updated backend services. Deploy the matching administration/customer portal clients together with the backend. The signature worker runs in the existing `stustapay-tse-controller` service (`stustapay tse signature-processor`); adding or changing server profiles and creating a TSE requires restarting that service so it discovers the configuration and TSE records. Do not apply these migrations or restart production services as part of an unverified TEST pilot.

Add a named profile under the global `fiskaly.profiles` configuration. The following is illustrative only; replace every placeholder locally and never commit credentials:

```yaml
fiskaly:
  profiles:
    test-pilot:
      api_key: "<TEST_API_KEY>"
      api_secret: "<TEST_API_SECRET>"
      environment: TEST
      request_timeout: 5
      max_concurrency: 8
      auto_provision_tss: true
      auto_provision_clients: true
      admin_pin: "<TEST_ADMIN_PIN_AT_LEAST_6_CHARACTERS>"
      puk_directory: "/var/lib/stustapay/fiskaly-puk"
```

This example enables automatic provisioning and is illustrative only; replace every placeholder locally and never commit secrets. Both `auto_provision_tss` and `auto_provision_clients` default to `false`. Automatic TSS provisioning requires `puk_directory` to be an absolute path; it must be owned by the service account with mode `0700`. The worker escrows each returned PUK before advancing TSS state, using a `0600` file. Provisioning either TSS or clients requires `admin_pin` as a secret of at least six characters. Use a secret-backed, access-controlled server configuration for `api_key`, `api_secret`, and `admin_pin`; keep it out of source control and restrict access. Do not put credentials in command-line arguments, logs, tickets, or API/admin fields. `environment` defaults to `TEST`; set `LIVE` only in a separately reviewed production profile with the intended LIVE credentials. The authentication claims' environment is checked before any remote resource creation.

Provision the directory and its parent before starting the controller. For the packaged service account, an operator can use `sudo install -d -m 0700 -o stustapay -g stustapay /var/lib/stustapay/fiskaly-puk`. Include the PUK directory in protected backups together with the database and preserve file ownership/permissions when restoring.

Create a TSE with `type=fiskaly` and set `fiskaly_profile` to the profile name. The worker persists a UUIDv4 TSS identity in the database. When `auto_provision_tss` is enabled and `tss_id` is omitted, it generates and persists that identity before contacting Fiskaly, then creates/initializes that exact TSS. With it disabled, configure the existing TSS UUID in `tss_id`. Never change or reuse a persisted TSS identity for another event.

With `auto_provision_clients: true`, the worker discovers tills that are unassigned or already assigned to this TSE, within the TSE's writable event/node visibility. It stores stable client UUIDv4 identities in `fiskaly_client_binding`, registers those same IDs remotely, and checks for new tills every 30 seconds. No manual client UUID map is needed in this mode. With automatic client provisioning disabled, retain the existing `clients` mapping from local till IDs to pre-provisioned Fiskaly client UUIDv4 IDs. Remote client `serial_number` must exactly equal the string form of its local till ID. Both modes verify client identity, TSS, environment, registration state, and visibility before local assignment. A till assigned to another TSE is not adopted. Verify intended scope and bindings before enabling provisioning because valid credentials and enabled flags permit remote resource creation. Do not deregister or replace historical TSS/client identities. Fiskaly profile identity cannot be changed after TSE initialization/use, and event-copy must not duplicate that identity.

Profile, TSS, provisioning flag, or client-map changes require restarting the backend process that runs the Fiskaly signature worker. Confirm the deployed process has loaded the intended profile after restart. A wrong administrator PIN stops the worker instead of repeatedly attempting admin authentication; correct the secure config and restart the controller. TSE profile changes are rejected once initialized or used; make corrections through a reviewed new TSE/profile setup, not by changing an established fiscal identity.

## TEST pilot

1. Obtain TEST credentials through the approved secret channel. Confirm the TEST organization and intended scope using an authorized operator account. No credentials are accessed by this runbook change.
2. Configure one named TEST profile and one dedicated pilot TSE. Choose either existing TSS/client bindings or automatic provisioning; for automatic setup, verify the admin PIN, PUK directory ownership/mode, event-node visibility and provisioning flags before restart. Confirm the remote TSS/client identities and environment after provisioning.
3. Select the Fiskaly profile in the administration UI, restart the controller, and confirm startup/configuration health without exposing credentials. For automatic clients, check that only tills within the writable event/TSE scope were bound and that their client IDs remain stable in the database.
4. Run a low-value representative operation and inspect its receipt and local DSFinV-K export. Verify the receipt signature/QR against actual Fiskaly TEST data; local simulator signatures are not cryptographic evidence.
5. Exercise an ambiguous timeout and a worker restart during pending work in TEST. Confirm recovery reconciles the same remote transaction and yields at most one fiscal transaction.
6. Expand to representative operation types, outage/recovery behavior, and a measured load pilot for up to 100 tills. Record throughput, queue delay, signing latency, and rate-limit behavior against agreed peak-volume thresholds.

The worker persists a transaction UUID, client UUID, and signing payload before sending a remote request. It uses a per-TSE PostgreSQL advisory lock, per-till ordering, and bounded concurrency. Retryable transport/upstream failures retain the row and use delayed retries; permanent failures are settled as `failure`. An ambiguous request or worker restart must be reconciled against Fiskaly using the same UUID and payload. Do not delete a failed/pending row or retry it with a newly generated UUID: that can create a second fiscal transaction. The database protects persisted identity and payload from edits. A booked operation remains booked if signing is pending or fails; signing starts after booking. Confirm that lifecycle for every in-scope operation before rollout. DSFinV-K export refuses to run while any signature is `new` or `pending`; settled failures are exported with an error, and no TSE identity is fabricated for a till that was never assigned.

The provisioning flow checks the Fiskaly authentication token's claimed environment against the configured TEST/LIVE environment before creating a TSS or client. TSS creation and initialization follow Fiskaly's SIGN DE operations reference: [Create TSS](https://workspace.fiskaly.com/api/sign-de/operations/createtss/). PUK escrow is a required safety step before the worker advances the TSS state.

## Automated multi-customer onboarding

The management-API onboarding workflow is implemented locally and covered by automated tests. Live Fiskaly credentials and resources have not been used to validate it. Do not use local test results as evidence that remote credentials, resources, or LIVE readiness have been verified.

The provider's central **teamfestlichPay** Account and Fiskaly Group are bootstrapped manually by an authorized provider operator. Customer nodes are then provisioned under that organization. A provider root administrator with `node_administration` creates or selects a customer-bound site (`customer_node_id`) and associates a site with an event. The administrator starts a durable asynchronous onboarding job for **TEST** or, as a separate explicit action, **LIVE**. Customer administrators may see only sites bound to their customer node and their setup status. A profile name or event selection alone must never establish authorization. All site and provisioning API calls require the `node_id` query parameter; authorization derives from the caller's access to that node, not the parameter alone.

The administration endpoints are `GET /fiskaly/sites/` and `POST /fiskaly/sites/` for listing and creating sites, `GET /fiskaly/sites/{id}/status` for setup status, `POST /fiskaly/provisioning/` to start a job, and `POST /fiskaly/provisioning/{id}/retry` to retry an eligible job. Each call includes `node_id` as a query parameter. Site creation records the Unit's `operator_name` and `vat_id`.

One site maps to one Fiskaly Unit and may be selected by multiple events. Each event can have only one environment: TEST and LIVE require separate events and separate jobs. The event/job association is immutable and unique, so do not retry or create a second environment job for the same event. Each event receives its own TSS/TSE identity and client registrations; do not copy an event's TSS identity or client bindings when copying an event. The job creates or reconciles the Unit, enables the requested environment, creates a dedicated Unit API key, persists the credential securely, and then uses the existing TSS/client provisioning path. TEST and LIVE credentials and TSS resources remain distinct. LIVE provisioning additionally requires provider-side LIVE activation, valid credentials, and billing/contract setup; those steps are manual prerequisites.

### Management configuration

The following is the intended shape for the management API configuration. It is illustrative, not a claim that a real organization or credentials have been configured. Keep values in secret-backed server configuration and out of source control:

```yaml
fiskaly:
  management:
    enabled: false
    secret_key: "<FERNET_KEY_FROM_SECRET_STORE>"
    puk_directory: "/var/lib/stustapay/fiskaly-puk"
    max_active_tses: 16
    environments:
      TEST:
        environment: TEST
        group_id: "<FISKALY_GROUP_ID>"
        api_key: "<MANAGEMENT_TEST_API_KEY>"
        api_secret: "<MANAGEMENT_TEST_API_SECRET>"
      LIVE:
        environment: LIVE
        group_id: "<FISKALY_GROUP_ID>"
        api_key: "<MANAGEMENT_LIVE_API_KEY>"
        api_secret: "<MANAGEMENT_LIVE_API_SECRET>"
```

Management is disabled by default. When enabled, `management.secret_key` is required and must be a dedicated Fernet key held outside the database. Generate it privately on the server or in an approved secret-management environment, for example with `python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`; keep the output directly in the approved secret store and never place it in documentation, source control, or a shared command transcript. Each environment entry requires an `environment` value equal to its map key (`TEST` or `LIVE`); a LIVE entry must explicitly say `LIVE`, because a default of TEST is invalid for LIVE. Entries also contain management credentials and the expected provider Group ID. `max_active_tses` defaults to 16 and is limited to 64; each additional slot adds a database connection to the controller pool, so size it against the database connection budget. Store the PUK directory as an absolute, private, service-owned path with mode `0700`. Backup and restore the database, runtime configuration/secret-store material (including the Fernet key and management credentials), and PUK directory together; preserve file ownership and permissions. The existing SIGN DE profile configuration remains supported. A YAML profile is provider-admin-only unless it has an explicit `customer_node_id` of at least 1 and expected `organization_id` binding. Never return or log management credentials, Unit API secrets, admin PINs, encryption keys, or PUK values.

### Job handling and operational limits

The durable job reports `queued`, `running`, `retry_wait`, `action_required`, `failed`, or `ready`. Repeated start requests must be idempotent. If a remote organization-creation request has an unknown outcome, do not blindly POST again; reconcile through an authorized read or operator intervention first. For other ambiguous management API responses, reconcile the intended resource using the persisted job identity and remote metadata before attempting creation again; never blindly create a duplicate Unit or key. If a one-time key secret was lost, mark the job `action_required`; an explicitly initiated retry may replace the key only when the job is still unfinished and no TSS was created. `ready` means the Unit/environment/key and the requested event TSS and clients have all been successfully provisioned.

The management API must validate that the selected customer belongs to the configured provider Group and that every Unit key and token is for the requested organization and environment. Keep secrets encrypted at rest and exclude them from API responses, logs, support output, and generated API specifications. Profile-based manual provisioning remains provider-only unless its `customer_node_id` is at least 1 and its expected `organization_id` is explicit; customer administrators can use only profiles with both bindings. Browser verification of the administration workflow and an actual Fiskaly TEST onboarding/signature remain pending.

### TSE and client capacity

Automatic client provisioning counts every till in the event, including the system virtual till. The remote TSE's reported `max_number_registered_clients` is authoritative; provisioning stops before client-registration HTTP requests when the event's total would exceed it. For example, a limit of 100 permits 99 physical tills plus the one virtual till; 101 total tills are rejected before any client is registered. One site may serve multiple events and therefore multiple event-specific TSEs. The system does not currently shard one event across multiple TSSs automatically. `management.max_active_tses` limits how many TSEs the controller handles concurrently (default 16, maximum 64); it is a controller/database-pool limit, not an increase to Fiskaly's per-TSE client capacity. No real Fiskaly cloud test has validated 100-client capacity.

The existing transaction-signing worker still signs after booking. Automated onboarding does not establish that this lifecycle is correct for every fiscal operation. Complete the documented transaction lifecycle assessment and a real TEST pilot covering signatures, receipts, exports, restart/recovery, event isolation, and up to 100 tills before enabling LIVE.

## Read-only queue and failure inspection

Use a read-only database session. These queries inspect local signature state; they do not establish the corresponding remote Fiskaly state. Column additions may evolve with the migration, so inspect the deployed schema before querying migration-specific UUID/payload fields.

```sql
-- Queue/status counts, including Fiskaly retry state
SELECT signature_status, count(*)
FROM tse_signature
GROUP BY signature_status
ORDER BY signature_status;

-- Persisted TSS and client identities (no credentials or PUKs)
SELECT id, name, fiskaly_profile, fiskaly_tss_id, status, last_error
FROM tse WHERE type = 'fiskaly';
SELECT tse_id, till_id, client_id, registered
FROM fiskaly_client_binding ORDER BY tse_id, till_id;

-- Recent failures for operator triage
SELECT id, tse_id, signature_status, result_message,
       fiskaly_transaction_id, fiskaly_attempts, fiskaly_next_attempt, fiskaly_last_error
FROM tse_signature
WHERE signature_status = 'failure'
ORDER BY id DESC
LIMIT 100;

-- Pending work and scheduled retry details
SELECT id, tse_id, signature_status, fiskaly_transaction_id,
       fiskaly_attempts, fiskaly_next_attempt, fiskaly_last_error
FROM tse_signature
WHERE signature_status IN ('new', 'pending')
ORDER BY id
LIMIT 100;

-- Persisted client identities and registration state for one TSE
SELECT till_id, client_id, registered
FROM fiskaly_client_binding
WHERE tse_id = CAST('<LOCAL_TSE_ID>' AS bigint)
ORDER BY till_id;
```

Do not include API keys, API secrets, or the full `fiskaly_request` signing payload in support output. For a Fiskaly failure, correlate the local row's persisted remote transaction UUID with the remote transaction state using the approved TEST/LIVE credentials and authorized Fiskaly tooling. A local `failure` status alone does not prove that Fiskaly did not complete the transaction.

## Recovery and escalation

- For queue growth, inspect counts and timestamps, worker logs, profile/TSS environment, client bindings, and Fiskaly service health. Logs and diagnostics must not contain credentials.
- For a timeout or process interruption, keep the original row and reconcile its persisted UUID and payload with Fiskaly. Resume only through the worker's same-transaction recovery path.
- For a completed remote transaction with a local failure/pending state, retain the record and escalate with the local signature row ID and remote UUID. Do not manually synthesize signature fields or create another transaction.
- For a permanent configuration error, correct the profile or binding, restart the worker, and verify recovery in TEST first. Do not edit/delete queued transaction identity or payload to make the worker proceed.
- If remote status cannot be established, stop retries for the affected work and escalate to the Fiskaly integration operator. Preserve database state and relevant sanitized logs for reconciliation.

## LIVE release gates

Do not select a LIVE profile until an actual TEST pilot has verified signatures, receipt/QR rendering, DSFinV-K mapping, recovery after ambiguous responses and restart, event/TSE isolation, and the agreed 100-till load criteria. Confirm transaction lifecycle coverage and unsigned-operation treatment across all included operation types. Then review the LIVE organization, TSS, client bindings, secret storage, and deployment configuration as a separate change. The current plan and implementation do not claim these gates have passed.
