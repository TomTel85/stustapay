# Fiskaly SIGN DE implementation plan

Planning baseline: 2026-10-10. A Fiskaly TEST organization is believed to exist, but its access and TSS state are unverified. This document plans implementation; no remote resources have been changed.

User priorities: go live as soon as possible; support up to 100 tills. First milestone is a verified TEST signature with receipt/export mapping, followed by recovery and a 100-till load pilot. Calendar estimates depend on TEST access and the transaction lifecycle assessment.

## Offline implementation progress

At the user's request, implementation proceeds without access to the TEST organization. The initial module under `stustapay/tse/fiskaly/` now contains typed secret-masked configuration, bounded HTTP transport, cached authentication with one 401 refresh, initialized TSS/environment checks, explicit client-binding verification, and raw Kassenbeleg-V1 start/finish signing. UUIDv4 transaction and client IDs are supplied by the caller; the signing module never invents a replacement transaction on failure. A payload fingerprint in transaction metadata prevents active recovery with changed data. Completed recovery also checks the returned raw payload and TSS signature metadata.

Local HTTP simulator tests cover lost start/finish responses followed by a new client/signer instance, mismatched identities/payloads/environments, token renewal, upstream errors, malformed signatures, timestamps, duplicate concurrent work and bounded concurrency for 100 distinct till bindings. These tests validate local protocol behavior; they do not measure Fiskaly service capacity or establish production readiness.

The second offline milestone wires the provider into global configuration, migration 70, the signature processor, and administration creation/edit/detail forms. The worker commits transaction/client UUIDs and payload before network I/O, preserves pending requests on restart, reconciles remote success after a missing local commit, and uses PostgreSQL ownership plus per-till ordering. Migration 71 and the provisioning worker support optional TSS initialization and client registration. Both provisioning flags default to false. Automatic TSS IDs and client IDs are persisted before use; automatic client discovery covers unassigned tills and tills already assigned to that TSE within its writable event/node visibility, then refreshes new bindings every 30 seconds. After startup the refresh verifies new bindings and keeps registered tills signing at capacity. Automatic provisioning validates the token environment claim before resource creation, escrows TSS PUKs in a service-owned mode-0700 directory using mode-0600 files before state advancement, and stops the worker on administrator authentication failure to avoid PIN lockout. Manual pre-provisioned TSS/client configuration remains supported. Fiskaly identities are immutable and reused by explicit taxpayer assignment.

Receipts remain available with missing/pending/failed signatures and only expose a QR for complete signatures. DSFinV-K export refuses open signatures instead of silently omitting booked operations; settled failures retain the operation without inventing a TSE identity. Admin/customer contracts and web clients are regenerated. The terminalserver contract is unchanged, so no Android client update is required.

Local validation covers durable recovery, immutable payloads, worker ownership, assignment isolation and receipt/export status: 518 full backend tests passed; the final focused suite passed 88 tests, including the later initialized-TSS disappearance regression. Both web production builds passed, along with administration/customerportal tests and three new actual form tests. Existing repository-wide lint blockers are documented in the QA handoff. The current implementation retains signing after booking; the complete business transaction lifecycle still needs assessment and actual TEST validation before LIVE. Synthetic provider responses do not establish cryptographic validity or cloud capacity. See [the operations runbook](fiskaly-operations.md) and `.agents/state/qa.md` for checks and remaining gates.

## Automated multi-customer onboarding scope

The follow-up onboarding increment automates Fiskaly Management API setup for the existing `teamfestlichPay` provider Account and Group. Bootstrap of that Account/Group, provider activation, LIVE access, contracts, and billing remain manual operator prerequisites. Provider root administrators create customer-bound sites linked to `customer_node_id`, select a site for each event, and start an asynchronous TEST job. LIVE stays disabled until checkout owns fiscal start and finish. A site maps to one Unit and can serve multiple events; managed deployments reuse their taxpayer’s TSS/TSE and available client identities. An event is bound to one environment only; TEST and LIVE use separate events and immutable, unique event/job associations.

The local implementation creates or reconciles a Unit using its `operator_name` and `vat_id`, enables the requested environment, creates a dedicated Unit API key, encrypts its secret using a dedicated server-side Fernet key, and hands off to the existing TSS/client provisioning path. Jobs persist progress through `queued`, `running`, `retry_wait`, `action_required`, `failed`, and `ready`; retries reconcile ambiguous remote outcomes and must not create duplicate resources. An unknown result from organization creation is never blindly retried. Lost key secrets may be replaced only through an explicit retry while the job is unfinished and before a TSS exists. PUK storage continues in an absolute, private `0700` directory. Management credentials, API-key secrets, admin PINs, Fernet keys, and PUKs must never be returned by APIs or written to logs.

The configuration uses `fiskaly.management.enabled` (default `false`), required `fiskaly.management.secret_key` when enabled, `fiskaly.management.puk_directory`, `fiskaly.management.max_active_tses` (default 16, maximum 64), and per-environment `fiskaly.management.environments.TEST` / `LIVE` entries containing `environment`, `group_id`, `api_key`, and `api_secret`. Each `environment` must match its map key. The controller adds up to `max_active_tses` database connections to its pool, so its value must fit the database connection budget. Existing YAML profiles remain supported; customer administrators may use one only when `customer_node_id` is at least 1 and expected `organization_id` is set. Unbound profiles remain provider-admin-only. The API surface is `GET/POST /fiskaly/sites/`, `GET /fiskaly/sites/{id}/status`, `POST /fiskaly/provisioning/`, and `POST /fiskaly/provisioning/{id}/retry`; every request includes the authorized `node_id` query parameter. Local implementation and automated tests are in place. No real Fiskaly TEST/LIVE credentials, resources, or cryptographic signatures have been validated.

Automatic provisioning counts every event till, including the system virtual till, against the TSE's reported `max_number_registered_clients`. It stops before client-registration HTTP requests if the limit would be exceeded (for example, 99 physical tills plus one virtual till fit a limit of 100; initial setup with 101 total tills is blocked). A site can serve multiple events, reusing its TSE and free clients; disjoint seller scopes can select other taxpayers. `management.max_active_tses` is the separate controller concurrency/database-pool limit and does not raise Fiskaly's per-TSE client limit. Simulated coverage for 100 till bindings is not evidence of 100-client cloud capacity; real TEST capacity validation remains pending.

### Onboarding implementation and validation status

- Local implementation includes customer/site persistence, provider/customer authorization, Unit Group/organization/environment validation, and the management configuration above.
- Local implementation includes durable job APIs and worker, encrypted credential storage, PUK-directory handling, and guarded recovery for lost one-time secrets.
- Local implementation includes administration UI for site selection, event association, starting TEST jobs, and progress/error/retry status without exposing secrets.
- Automated local coverage is in place for onboarding behavior. Browser verification and a real TEST onboarding plus representative signature remain pending; validate shared-site multi-event isolation, duplicate requests, worker restart, ambiguous API outcomes, and recovery against the actual service.
- Measure actual remote `max_number_registered_clients` and validate the 100-client scenario in Fiskaly TEST, accounting for the virtual till. Do not infer remote capacity from local simulator or concurrency tests.
- Confirm provider-side LIVE activation and billing, then complete existing transaction lifecycle, receipt/export, and 100-till gates before declaring LIVE readiness.

## Goal

Integrate Fiskaly SIGN DE v2 with StuStaPay and validate a complete TEST operation before enabling LIVE. Retain Diebold Nixdorf support. Support either an explicitly configured, pre-provisioned TSS/client setup or opt-in automatic TSS initialization and client registration. Fiskaly DSFinV-K API integration remains a separate follow-up; continue using the existing local DSFinV-K export after validating its Fiskaly mappings.

## Delivery sequence

1. **Verify access and settle the transaction lifecycle.** Verify TEST credentials through a secure local credential source, organization environment, existing TSS initialization, master data, and client registrations. Inspect the current API schema for transaction payloads and signature fields. Confirm which process-data representation supports the existing Kassenbeleg_V1 generation. Document where each relevant business operation starts and finishes, including sale, cancellation/refund, top-up, payout, ticket purchase, cashier transfers, failed checkout and offline import. The current worker signs after booking; do not assume this is sufficient for the intended production transaction lifecycle. If earlier starts are needed, include backend/terminal contract changes in scope before declaring readiness.

2. **Add provider configuration and data model.** Add the Fiskaly provider enum, correctly chained migrations, TSS identifier, credential-profile reference, configurable timeouts, and stable client bindings. Keep API credentials, admin PIN and PUK out of API responses, generated specs, logs and committed config. Support TEST/LIVE profiles and validate token claims and remote resource environments before provisioning. Persist provider type on creation and preserve existing Diebold records/forms. Treat TSS identity and client bindings as fiscal identities, not ordinary copyable event configuration.

3. **Implement transport and adapter.** Add a dedicated HTTP client and TSEHandler adapter for authentication/token renewal, TSS master data, client verification, and transaction start/finish/query. Support opt-in, idempotent creation/initialization of a TSS and registration of clients using stable persisted UUIDs; till integer IDs alone are not Fiskaly UUIDs. For automatic TSS setup, persist the generated identity and durably escrow the returned PUK in an absolute service-owned mode-0700 directory with mode-0600 files before advancing TSS state. Automatic clients discover only unassigned or same-TSE tills within writable event visibility, persist IDs before remote writes, and refresh discovery every 30 seconds. Retain the explicit pre-provisioned mapping mode. Use durable transaction UUIDs and revisions. Map transaction number, counter, timestamps, algorithm, public key, certificate and signature encoding to existing receipt/export models. Use bounded requests and sanitized logging. Never change or deregister historical fiscal resources during normal operation.

4. **Harden processing and recovery.** Persist signing payload and remote identity before requests; preserve the payload across retries. After ambiguous timeouts or process restarts, query the same remote transaction and reconcile its state before any repeat write. Handle completed remote signatures whose database update failed. Separate recoverable communication failures from recorded fiscal outages and permanent configuration errors. Remove unconditional startup failure of pending Fiskaly work. Enforce one active worker ownership per transaction. Validate assignment within event/node visibility and prefer explicit TSS assignment. Bound concurrency based on the number of tills and provider limits; avoid unbounded backlog with the existing serial worker.

5. **Finish operator and receipt behavior.** Add provider-specific administration fields, assignment, connection/signing health and actionable failure messages. Expose no secrets. Define whether TSE additions/config changes require worker restart or implement safe reload. Keep receipts available for unsigned/pending orders, including orders with no TSE assignment; generate signature QR content only for completed signatures and display an appropriate failure/pending indication otherwise. DSFinV-K export now refuses to run with `new`/`pending` signatures and exports settled failures with an error; validate local export mappings and operator workflow. Handle offline-originated orders explicitly without inventing historical cloud signature timestamps. Wrong admin PIN must stop provisioning attempts until secure config is corrected and the controller restarted, avoiding account lockout.

6. **Validate and roll out.** Run targeted automated tests and repo-required checks; then verify actual signing against the existing TEST organization. Pilot representative tills and payment/order types, receipt rendering and QR verification, DSFinV-K output, outages, recovery, process restart and realistic concurrency. Enable LIVE only after the acceptance criteria below are met, with explicit operational rollout authorization and a verified live credential/TSS profile.

## Acceptance criteria

- Every in-scope fiscal operation attempts signing through a documented lifecycle; source order timestamps and TSE timestamps remain distinguishable.
- Completed signatures persist accurately and produce verifiable receipts and DSFinV-K records.
- Missing signatures retain the booked operation, produce usable receipts with status, and appear in exports with a recorded failure reason.
- A timeout after remote success and a restart between remote success and database commit do not create duplicate fiscal transactions.
- Pending work recovers without indefinite blocking; authentication, rate limits, upstream outages and permanent errors have bounded, visible handling.
- A 100-till concurrent workload is validated with measured throughput, queue delay, signing latency and rate-limit behavior. Use bounded concurrency and explicit per-transaction ownership, with per-till ordering wherever the business lifecycle requires it; set numeric pass thresholds from expected peak transaction volume before the load pilot.
- Kassen assignments cannot cross unrelated events/organizations; client identities survive restart and do not collide across installations.
- Automatic provisioning remains opt-in; before creating remote resources, token environment claims must match the selected TEST/LIVE profile. PUK escrow must be durable before TSS state advances, and wrong admin PIN stops the worker pending configuration correction and restart.
- Diebold behavior remains supported and regression-tested.
- TEST credentials/TSS cannot accidentally be used as the production profile; no credentials appear in logs or API data.
- Actual Fiskaly TEST pilot passes before production readiness is asserted.

## Affected surfaces and generated artifacts

Backend: stustapay/tse, configuration, TSE schema/service, migrations, administration routes, receipt and DSFinV-K code, tests. Web: administration TSE forms/status, translations, shared models. Operations: config examples and controller runbook/service behavior. Potential terminal/Android scope depends on the lifecycle decision in step 1.

Run make sync-contract for schema/route changes. Review api/*.json, web generated clients, and app/api separately from handwritten changes. Android implementation changes are conditional on lifecycle/receipt contract impact, not required merely to host a cloud adapter on the backend.

## Required checks

- make verify-backend
- make verify-web-administration
- make verify-web-customerportal when shared web models/libraries change (expected)
- make sync-contract and generated-diff review
- make verify-android if Android source or generated Android clients change
- Browser QA of provider configuration, assignment, health and failure states
- Manual secret/config/deployment review and real Fiskaly TEST smoke/pilot

Targeted tests must cover token expiry/401, start/finish payloads and revisions, signed response mapping, timeout after success, restart recovery, duplicate delivery, worker ownership, event isolation, missing-assignment receipts, unsigned exports and Diebold regression. Review money/VAT mappings for refunds, top-ups and special order types using fixture-backed data.

## Open inputs

- Concrete deadline and peak transactions per second; user target is as soon as possible with up to 100 tills.
- Secure local availability of TEST API credentials and administrator PIN, intended organization, and whether to use existing TSS/client identities or opt-in automatic provisioning.
- Intended LIVE organization/TSS and multi-event deployment model.
- Whether offline sales will be enabled during the first pilot.
- Transaction lifecycle decision from step 1, which determines any additional Android/backend contract work.

## Primary references

- https://workspace.fiskaly.com/countries/germany/quickstart/
- https://workspace.fiskaly.com/api/sign-de/operations/createtss/
- https://workspace.fiskaly.com/api/
- https://workspace.fiskaly.com/countries/germany/guides/error-handling/
