# Fiskaly SIGN DE operations

StuStaPay supports SIGN DE signing, retry and reconciliation, administration profile selection, and multi-customer onboarding. The 2026-11-14 SIGN DE TEST pilot verified checkout start, finish, cancellation, receipt QR data, the local DSFinV-K ZIP, and the remote TSE TAR. The LIVE release gates below remain in effect.

## Configuration

This increment requires migrations `0000070` through `0000078` before starting the updated backend services. Deploy the matching administration/customer portal clients together with the backend. The signature worker runs in the existing `stustapay-tse-controller` service (`stustapay tse signature-processor`); adding or changing server profiles and creating a TSE requires restarting that service so it discovers the configuration and TSE records. Do not apply these migrations or restart production services as part of an unverified TEST pilot.

Databases that ran the earlier Fiskaly branch used migration IDs 63–65 for different SQL. Use a fresh TEST database or a database with the current upstream migration history for this branch. Preserve any existing pilot database with fiscal records for separate reconciliation.

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

This example enables automatic provisioning and is illustrative only; replace every placeholder locally and never commit secrets. Both `auto_provision_tss` and `auto_provision_clients` default to `false`. Automatic TSS provisioning requires `puk_directory` to be an absolute path; it must be owned by the service account with mode `0700`. The worker escrows each returned PUK before advancing TSS state, using a `0600` file. Provisioning either TSS or clients requires `admin_pin` as a secret of at least six characters. Use a secret-backed, access-controlled server configuration for `api_key`, `api_secret`, and `admin_pin`; keep it out of source control and restrict access. Do not put credentials in command-line arguments, logs, tickets, or API/admin fields. `environment` defaults to `TEST`. The application rejects LIVE Fiskaly onboarding and signing until checkout owns the fiscal start and finish. The authentication claims' environment is checked before any remote resource creation.

Provision the directory and its parent before starting the controller. For the packaged service account, an operator can use `sudo install -d -m 0700 -o stustapay -g stustapay /var/lib/stustapay/fiskaly-puk`. Include the PUK directory in protected backups together with the database and preserve file ownership/permissions when restoring.

Create a TSE with `type=fiskaly` and set `fiskaly_profile` to the profile name. The worker persists a UUIDv4 TSS identity in the database. When `auto_provision_tss` is enabled and `tss_id` is omitted, it generates and persists that identity before contacting Fiskaly, then creates and initializes that TSS. With automatic provisioning disabled, configure the existing TSS UUID in `tss_id`. For reuse across events, link a managed deployment to the existing taxpayer and TSE as described below.

With `auto_provision_clients: true`, the worker discovers tills that are unassigned or already assigned to this TSE, within the TSE's writable event/node visibility. It stores stable client UUIDv4 identities in `fiskaly_client_binding`, registers those same IDs remotely, and checks for new tills every 30 seconds. The controller verifies existing bindings at startup. Once a TSE is active, reaching capacity keeps existing tills signing and lists excess unassigned till IDs in the TSE error. Restart the controller after the provider raises the TSS capacity. No manual client UUID map is needed in this mode. With automatic client provisioning disabled, retain the existing `clients` mapping from local till IDs to pre-provisioned Fiskaly client UUIDv4 IDs. Remote client `serial_number` must exactly equal the string form of its local till ID. Both modes verify client identity, TSS, environment, registration state, and visibility before local assignment. A till assigned to another TSE is not adopted. Verify intended scope and bindings before enabling provisioning because valid credentials and enabled flags permit remote resource creation. Do not deregister or replace historical TSS/client identities. Fiskaly profile identity cannot be changed after TSE initialization/use, and event-copy must not duplicate that identity.

Profile, TSS, provisioning flag, or client-map changes require restarting the backend process that runs the Fiskaly signature worker. Confirm the deployed process has loaded the intended profile after restart. A wrong administrator PIN stops the worker instead of repeatedly attempting admin authentication; correct the secure config and restart the controller. TSE profile changes are rejected once initialized or used; make corrections through a reviewed new TSE/profile setup, not by changing an established fiscal identity.

## TEST pilot

1. Obtain TEST credentials through the approved secret channel. Confirm the TEST organization and intended scope using an authorized operator account.
2. Configure one named TEST profile and one dedicated pilot TSE. Choose either existing TSS/client bindings or automatic provisioning; for automatic setup, verify the admin PIN, PUK directory ownership/mode, event-node visibility and provisioning flags before restart. Confirm the remote TSS/client identities and environment after provisioning.
3. Select the Fiskaly profile in the administration UI, restart the controller, and confirm startup/configuration health without exposing credentials. For automatic clients, check that only tills within the writable event/TSE scope were bound and that their client IDs remain stable in the database.
4. Run a low-value representative operation and inspect its receipt and local DSFinV-K export. Verify the receipt signature/QR against actual Fiskaly TEST data; local simulator signatures are not cryptographic evidence.
5. Exercise an ambiguous timeout and a worker restart during pending work in TEST. Confirm recovery reconciles the same remote transaction and yields at most one fiscal transaction.
6. Expand to representative operation types, outage/recovery behavior, and a measured load pilot for up to 100 tills. Record throughput, queue delay, signing latency, and rate-limit behavior against agreed peak-volume thresholds.

The worker persists the transaction and client UUIDs before the first remote request and the signing payload before finishing. It uses a per-TSE PostgreSQL advisory lock, per-till ordering, and bounded concurrency. Retryable errors use delayed retries, including the provider's `Retry-After` delay. After eight attempts, or a non-retryable error on a persisted transaction, the worker pauses that transaction for reconciliation (`fiskaly_next_attempt = 'infinity'`). Later orders on the same till can sign. The paused order remains pending and the export reports its order ID until an operator settles it. Reconcile an ambiguous request or worker restart against Fiskaly using the same UUID and payload. The database protects persisted identity and payload from edits. Bookings remain valid if signing is pending or fails. DSFinV-K export refuses to run while any signature is `new` or `pending` and includes the error for settled failures.

The provisioning flow checks the Fiskaly authentication token's claimed environment against the configured TEST/LIVE environment before creating a TSS or client. TSS creation and initialization follow Fiskaly's SIGN DE operations reference: [Create TSS](https://workspace.fiskaly.com/api/sign-de/operations/createtss/). PUK escrow is a required safety step before the worker advances the TSS state.

## Automated multi-customer onboarding

Automated tests cover the management-API onboarding workflow. The checkout pilot reused a managed TEST organization, TSE, and registered client from the earlier onboarding pilot.

The provider's central **teamfestlichPay** Account and Fiskaly Group are bootstrapped manually by an authorized provider operator. Customer nodes are then provisioned under that organization. A provider root administrator with `node_administration` creates or selects a customer-bound site (`customer_node_id`) and associates a site with an event. The administrator can start a durable asynchronous onboarding job for **TEST**. Customer administrators may see only sites bound to their customer node and their setup status. A profile name or event selection alone must never establish authorization. All site and provisioning API calls require the `node_id` query parameter; authorization derives from the caller's access to that node, not the parameter alone.

The administration endpoints are `GET /fiskaly/sites/` and `POST /fiskaly/sites/` for listing and creating sites, `GET /fiskaly/sites/{id}/status` for setup status, `POST /fiskaly/provisioning/` to start a job, and `POST /fiskaly/provisioning/{id}/retry` to retry an eligible job. Each call includes `node_id` as a query parameter. Site creation records the Unit's `operator_name` and `vat_id`.

One site maps to one Fiskaly Unit and may be selected by multiple events. Each event can have only one environment. A future LIVE rollout will require a separate event and job. The event/job association is immutable and unique, so do not retry or create a second environment job for the same event. Managed deployments reuse the taxpayer’s existing TSS/TSE and available client identities. Copied events need an explicit taxpayer assignment. The job creates or reconciles the Unit, enables the requested environment, creates a dedicated Unit API key, persists the credential securely, and then uses the existing TSS/client provisioning path. TEST and LIVE credentials and TSS resources remain distinct. LIVE provisioning additionally requires provider-side LIVE activation, valid credentials, and billing/contract setup; those steps are manual prerequisites.

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
```

Management is disabled by default. When enabled, `management.secret_key` is required and must be a dedicated Fernet key held outside the database. Generate it privately on the server or in an approved secret-management environment, for example with `python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`; keep the output directly in the approved secret store and never place it in documentation, source control, or a shared command transcript. Each environment entry requires an `environment` value equal to its map key (`TEST` or `LIVE`). Only TEST jobs run in this release. Entries also contain management credentials and the expected provider Group ID. `max_active_tses` defaults to 16 and is limited to 64; each additional slot adds a database connection to the controller pool, so size it against the database connection budget. Store the PUK directory as an absolute, private, service-owned path with mode `0700`. Backup and restore the database, runtime configuration/secret-store material (including the Fernet key and management credentials), and PUK directory together; preserve file ownership and permissions. The existing SIGN DE profile configuration remains supported. A YAML profile is provider-admin-only unless it has an explicit `customer_node_id` of at least 1 and expected `organization_id` binding. Never return or log management credentials, Unit API secrets, admin PINs, encryption keys, or PUK values.

### Job handling and operational limits

The durable job reports `queued`, `running`, `retry_wait`, `action_required`, `failed`, or `ready`. Repeated start requests must be idempotent. If a remote organization-creation request has an unknown outcome, do not blindly POST again; reconcile through an authorized read or operator intervention first. For other ambiguous management API responses, reconcile the intended resource using the persisted job identity and remote metadata before attempting creation again; never blindly create a duplicate Unit or key. If a one-time key secret was lost, mark the job `action_required`; an explicitly initiated retry may replace the key only when the job is still unfinished and no TSS was created. `ready` means the Unit/environment/key and the requested event TSS and clients have all been successfully provisioned.

The management API must validate that the selected customer belongs to the configured provider Group and that every Unit key and token is for the requested organization and environment. Keep secrets encrypted at rest and exclude them from API responses, logs, support output, and generated API specifications. Profile-based manual provisioning remains provider-only unless its `customer_node_id` is at least 1 and its expected `organization_id` is explicit. Customer administrators can use only profiles with both bindings.

### TSE and client capacity

The remote TSE's `max_number_registered_clients` limits registered clients. Count only tills assigned to terminals. An initial deployment that exceeds the available capacity is rejected. Active deployments of the same taxpayer share that TSE's capacity. `management.max_active_tses` limits controller and database-pool usage across TSEs (default 16, maximum 64). A 100-client cloud load test remains open.

Before enabling LIVE, extend the TEST pilot to restart/recovery, event isolation, representative operation types, and up to 100 tills.

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

### Resume or settle a paused TEST signature

Use the order ID reported by the controller or export and confirm the matching transaction UUID in the diagnostics above. If the original operation can be retried after recovery, requeue the paused row through PostgreSQL. The controller retrieves the original transaction before making another write and saves an existing completed signature if one is present.

```sql
UPDATE tse_signature
SET fiskaly_attempts = 0, fiskaly_next_attempt = now()
WHERE id = CAST('<ORDER_ID>' AS bigint)
  AND fiskaly_transaction_id = CAST('<TRANSACTION_UUID>' AS uuid)
  AND signature_status = 'pending'
  AND fiskaly_next_attempt = 'infinity';
```

If Fiskaly confirms the original transaction is absent or cancelled and the order must be reported unsigned, record the confirmed outcome and incident reference. Leave the identity and request intact. A finished transaction should be recovered through the worker. Leave an unknown outcome pending for reconciliation.

```sql
UPDATE tse_signature
SET signature_status = 'failure',
    result_message = '<CONFIRMED OUTCOME AND INCIDENT REFERENCE>'
WHERE id = CAST('<ORDER_ID>' AS bigint)
  AND fiskaly_transaction_id = CAST('<TRANSACTION_UUID>' AS uuid)
  AND signature_status = 'pending'
  AND fiskaly_next_attempt = 'infinity';
```

## LIVE release gates

LIVE stays unavailable until checkout implements the fiscal transaction lifecycle. The TEST pilot must also verify signatures, receipt/QR rendering, DSFinV-K mapping, recovery after ambiguous responses and restart, event/TSE isolation, and the agreed 100-till load criteria. Confirm transaction lifecycle coverage and unsigned-operation treatment across all included operation types. Then review the LIVE organization, TSS, client bindings, secret storage, and deployment configuration as a separate change. The current plan and implementation do not claim these gates have passed.

## Reusable clients and seller scopes

Migration 73 preserves existing TSS and client identities. For new managed deployments, select the same taxpayer record for each event. To give independent sellers their own TSEs within one event, create a taxpayer record for each seller and submit setup from that seller's event subnode. Seller scopes within an event must be disjoint. The service rejects a new deployment when more than one active legacy TSE already belongs to that taxpayer and environment. Reconcile legacy TSEs and preserve their exports before any retirement.

Set the event end time in the event settings. At that time, all managed Fiskaly deployments for the event stop starting new fiscal transactions. The controller checks every 30 seconds and deregisters clients as their open work settles. At 47 hours after the event end, deregistration proceeds even if a transaction still needs reconciliation, leaving an hour for retries before the 48-hour deadline. Unresolved transactions and their client identities stay recorded, and the controller reserves those clients until reconciliation. A client needed by another active deployment stays registered. If the controller or Fiskaly is unavailable, deregistration resumes when service is restored.

Activating the TSE registers only tills assigned to terminals, including for future events. Reactivating a paused deployment also registers its eligible clients on the controller's next refresh. Registration timing follows the operator's activation. Assign terminals only to the physical tills planned for use. Keep spare devices unassigned and assign a replacement to the original till so it keeps its client identity. A later terminal assignment triggers registration on the next controller refresh, normally within 30 seconds. Unassigned tills, including the virtual till, receive no fiscal client. Central bookings through an unassigned virtual till are recorded unsigned. The administration setup status warns 48 hours before month-end if an ended event's locally tracked clients remain registered without an active assignment. The warning stays visible after month-end while those clients remain registered. Check the actual registration state in fiskaly HUB and confirm the billing timezone before using the schedule in LIVE.

For events without an end time or for early shutdown, use **Pause registers**. The controller keeps the original IDs and serials so a later event can reuse the clients. **Resume registers** is available before the event end if the bindings are free. Check the fiscal client's state in the fiskaly HUB before relying on a billing-month boundary.

The SIGN DE controller records detected outage start, end and reason in `fiskaly_till_outage` per till. Bookings during a detected outage get an unsigned receipt. Offline sales imported into the fiscal journal keep an unsigned entry. For an ambiguous response the worker retrieves the persisted transaction ID and can reconcile an existing transaction. Once a remote attempt was made it will never start a new transaction for the same booked order. The remaining first-attempt TEST pilot path still starts after the booking.

Run `dsfinvk-export --node-id <event-or-customer-node> --taxpayer-id <site> --filename <file.zip>` for a managed seller; add `--till-id <id>` for one till. When the scope includes several fiscal owners, select a taxpayer or till to export. Exported seller details come from the taxpayer associated with the original booking.

Run `tse fiskaly-export --tse-id <local-id> --start <unix-seconds> --end <unix-seconds> --output <file.tar>` outside selling hours. When the export is pending, retry with the same parameters and path to reuse the saved export ID. Keep the TAR and its JSON sidecar in the protected fiscal archive. Use separate ranges for exports above fiskaly's record limit. Confirm both archives and the receipt QR against a real TEST signature as part of the pilot.


## SIGN DE TEST smoke test

Use a protected local StuStaPay configuration with a named Fiskaly profile containing `environment: TEST`, the expected `organization_id`, the initialized `tss_id`, and a `clients` mapping with an already registered TEST register. The test checks the environment and organization before any writes. It starts a synthetic €1 transaction, finishes it with the same ID and reads the signature back. It uses no payment provider or local database. Run the command again with `--abort` to test cancellation of a separate synthetic checkout. Keep the printed transaction ID if the connection drops. Re-run with `--recover <uuid>` to look up that ID and finish it if it is still active.

```sh
python3 -m stustapay -c /path/to/protected-config.yaml tse fiskaly-smoke --profile test-pilot --till-serial 123
```

The TEST terminal sale flow queues its fiscal start when the server validates the checkout. Booking can proceed during an outage. If booking wins the race against the queued start, the operation is recorded unsigned. The worker finishes a known start with the booked payload. Explicit abandonment asks the worker to cancel the same transaction. An idle checkout with no pending card payment is eligible for cancellation after 15 minutes. The 15-minute rule is a TEST fallback for terminals that lose their connection. Other types of fiscal operations and earlier cart-entry handling remain LIVE gates.

On 2026-11-14, the terminal API and worker used existing TEST register 1003. Transaction `22640fbd-e792-47a5-9171-df6f405d00a2` was `ACTIVE` before booking and `FINISHED` afterward. Its receipt QR data and DSFinV-K signature fields matched SIGN DE. Transaction `b21668d7-9658-48a4-9acb-318dc201941d` went from `ACTIVE` to `CANCELLED` without a booking. The TSE TAR under export ID `0e3e9472-7188-4618-9098-6a07581b76a4` included logs for both transactions and the X.509 certificates.

The event-end pilot used dedicated TEST client `7dc27407-a789-45d5-958a-db7e6de08f33`. After setting the test event's end time in the past, the controller refresh moved that client from `REGISTERED` to `DEREGISTERED`. SIGN DE TEST also accepted deregistration while a synthetic checkout was open. The checkout was resolved afterward and the client was left deregistered. Automated tests cover the 47-hour threshold and a failed deregistration request followed by a successful retry.
