# System optimization investigation

Date: 2026-10-02

Implementation update: the first optimization batch is now implemented locally. The findings below describe the original investigation; see the implementation and validation record at the end for current status.

Scope: source review of backend/database, payment processing, administration and customer web apps, Android terminal, and report generation. No production access, profiling, or load tests were performed. Impact rankings are engineering estimates; measured speedups are not available. Runtime behavior was not changed.

## Ranked opportunities

| Priority | Opportunity | Expected benefit | Effort | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Bound mail claims and shorten mail transactions | More reliable queue processing; lower memory and connection usage | Medium | Confirmed unbounded batch and SMTP inside transaction |
| 2 | Shorten payment transactions and batch pending work | Faster reconciliation under provider delays; fewer occupied connections and locks | High | Confirmed sequential external calls inside transaction |
| 3 | Batch sale product reads and line-item writes | Fewer database calls on each sale | Medium | Confirmed per-button reads and per-line writes |
| 4 | Filter pending topups by customer in SQL | Lookup cost scales with one customer's pending orders | Medium | Confirmed all-customer fetch and Python filtering |
| 5 | Remove final Android failure delay; improve retry scheduling | One second faster failure feedback; smoother recovery after outages | Small–medium | Confirmed extra delay and deterministic retry schedules |
| 6 | Restore stats timing and reduce background polling | Measurable dashboard cost; fewer unnecessary requests | Small–medium | Timing wrapper is a no-op; polling helper lacks focus suppression |
| 7 | Split web routes into asynchronously loaded bundles | Less JavaScript required for initial navigation | Medium | Routers statically import route components |
| 8 | Limit and time out report compilation | Controlled CPU/process usage during concurrent exports | Medium | Compiler launches have no local concurrency limit or timeout |

## 1. Mail queue: fix pacing and bound the work claimed

Evidence: `stustapay/core/service/mail.py:165–211` claims every due message, including attachments, under one five-minute lease and sends the resulting list sequentially. `_send_mail` at line 220 is transaction-decorated and performs SMTP I/O before recording the result.

The configured `timedelta(seconds=0.05)` is passed to `asyncio.sleep` through `.seconds`, which evaluates to zero. A local Python check confirmed this; `.total_seconds()` returns 0.05. This is a pacing defect, rather than a speed improvement: correcting it restores the intended sending limit.

A batch taking longer than five minutes can leave unsent messages eligible for another worker while the first still holds them in memory. `SKIP LOCKED` protects the initial claim, but does not renew its lease during later sequential sending. Duplicate delivery is therefore a conditional risk under backlog or slow SMTP.

Recommended work:

- Restore the intended delay with `.total_seconds()`.
- Claim a bounded number of messages, with batch size chosen against measured SMTP latency and lease duration.
- Keep claim and acknowledgement transactions short; perform SMTP outside them.
- Use claim ownership and lease renewal where needed, so stale workers cannot acknowledge work reassigned to another worker.
- Consider SMTP connection reuse per settings group after correctness is established.

Validation: extend `stustapay/tests/test_mail_service.py` for pacing, bounded claims, lease expiry, two workers, slow SMTP, and crashes around acknowledgement. SMTP and the database cannot provide atomic exactly-once delivery; preserve retry behavior and document the remaining crash window.

## 2. Payments: external I/O extends database work

Evidence: `stustapay/core/service/order/sumup.py:705–724` holds a database connection for the entire pending batch and processes each order inside a serializable transaction. `process_pending_order` at line 273 calls the external checkout API before booking. `stustapay/payment/sumup/api.py:244–290` creates a new HTTP session per GET/POST, with a ten-second request timeout.

For illustration, 100 sequential checks each taking one second imply roughly 100 seconds of provider wait before database work and the polling sleep. This is an illustrative bound on that workload, not a benchmark.

Online topup creation also locks the customer's account at `sumup.py:444`, then calls `find_checkout` at line 452. Slow provider responses can therefore delay competing changes to that account.

Recommended work:

- Fetch bounded due work and introduce an explicit claim mechanism before adding multiple workers.
- Perform provider status reads outside booking transactions where safe.
- Re-read and lock local state before the short atomic booking step; preserve UUID idempotency and paid-order reconciliation.
- Retry serialization failures around a fresh complete transaction. The current internal retry loop is called inside the worker's surrounding transaction, and inner broad exception handling can swallow serialization failures.
- Reuse a lifecycle-managed HTTP session with request-scoped authorization headers, preserving merchant isolation and shutdown cleanup.
- Add bounded provider concurrency only after claiming and booking correctness are verified.

Validation: provider delays/timeouts, multiple workers, customer-triggered checks racing the worker, serialization failures, duplicate paid responses, restart recovery, and multi-event merchant isolation. Measure oldest pending age, processing rate, pool wait, and transaction duration.

## 3. Sale path: reduce database round trips

Evidence: `_get_products_from_buttons` in `stustapay/core/service/order/order.py:294–336` executes a product query per button. `book_order` in `stustapay/core/service/order/booking.py:126–139` inserts each line separately. `book_prepared_bookings` at line 26 invokes the database booking function once per prepared transfer.

These portions perform B + L + T awaited database calls for B buttons, L resulting lines, and T transfers, in addition to the other sale checks and order insertion.

Recommended work: fetch requested button/product definitions in bulk and reconstruct the original positions; bulk-insert line items using an array/record input joined to tax rates. Retain price, returnability, profile visibility, restriction, ordering, and tax snapshot semantics. Preserve `book_transaction` behavior rather than replacing it with raw inserts: it normalizes negative transfers, rounds amounts, and updates balances and vouchers.

Shared system-account balance updates may also become a contention point: `stustapay/core/schema/db_code/0004-functions.sql:47–49` updates both accounts for every transfer. This is a hypothesis requiring lock measurements; batching client calls will not eliminate those row updates.

Validation: compare query counts and sale latency for 1/5/20 positions, including bundles, repeated products, returns, variable prices, vouchers, and concurrent sales. Reconcile balances and ledger entries exactly.

## 4. Pending online topup lookup scans other customers' orders

Evidence: `stustapay/core/service/order/pending_order.py:49–63` fetches all pending non-shared cashier-less topups, sorts them, deserializes their payloads, and only then compares customer ID and payment method. Its caller already holds the customer's account lock.

Recommended work: make customer ID and payment method queryable in SQL, preferably through explicit persisted fields with a migration/backfill. A version-aware JSON predicate is an alternative to assess against the current payload representation. Apply customer/payment filters and `LIMIT 1` in SQL, preserving newest-first selection and shared-order exclusion. Choose any index from representative execution plans.

Validation: multiple customers/events, legacy payload versions, multiple pending checkouts, shared orders, and large unrelated backlogs. Measure rows fetched and account lock duration.

## 5. Android: avoid delay after the final attempt

Evidence: `app/app/src/main/java/de/stustapay/stustapay/repository/InfallibleRepository.kt:152–200` has `maxAttempts = 1`, but sleeps for one second on failure before recording the failed request and publishing the response. The delay schedules no further attempt at that layer.

Remove that final delay while preserving durable failed-request state and manual retry behavior. This saves one second on that failure path; it does not affect lower-layer HTTP retries.

`TerminalConfigRepository.kt:128–140` retries failed configuration fetches at a fixed one-second interval. `net/TerminalApiAccessorInner.kt:261–265` uses deterministic HTTP retry delays. A fleet recovering together can produce synchronized load. Consider bounded backoff with jitter, cancellation, and connectivity awareness, while preserving prompt operator recovery and payment idempotency. Do not generalize all financial requests into unrestricted retries.

Validation: failed response publication, stored failure state, manual retry, cancellation, intermittent connectivity, and device recovery after a shared outage.

## 6. Dashboard: measure before rewriting queries

Evidence: `_timed_stats_query` at `stustapay/core/service/order/stats.py:270–280` discards timing context and simply awaits the query. The administration polling helper at `web/apps/administration/src/app/routes/nodes/stats/queryOptions.ts:1–6` does not request polling suppression while unfocused.

Restore query duration measurements and capture slow-query plans on representative data. Add suppression of polling in unfocused tabs, retaining focus/reconnect refresh. Consider short-lived, scope-aware aggregate caches only if measurements show repeated expensive queries and a clear freshness budget exists.

Existing optimizations should be preserved: `NodeStats.tsx` gates queries by expanded sections, prediction is opt-in and polls no faster than five minutes, and backend product/statistics queries already use scoped/materialized filtering. There is no basis from source alone to prescribe arbitrary extra indexes or a dashboard rewrite.

Validation: hidden tab request counts, focus/reconnect behavior, filter changes, access boundaries, and slow-query plans. Measure query time, rows read, endpoint latency, and requests per active dashboard.

## 7. Web: route-level loading

Evidence: `web/apps/administration/src/app/Router.tsx:1–98` imports the application's screens, including stats, reports, exports, and device administration, synchronously. `web/apps/customerportal/src/app/Router.tsx:4–16` similarly imports its routes.

Introduce asynchronous route loading, starting with the larger administration features. Preserve privilege guards and usable loading/error states. Measure production chunks before and after; existing Suspense boundaries alone do not make static imports asynchronous.

Validation: both initial and direct-link navigation, auth redirects, route failures, and production bundle transfer/parse costs. Actual savings require a production bundle analysis.

## 8. PDF reports: bound compiler resource use

Evidence: `stustapay/bon/pdflatex.py:101–134` launches `latexmk` and awaits completion without a timeout or local concurrency cap. Revenue, payout, and accounting reports use this path. Ordinary receipt data follows a separate path; this finding concerns report PDFs.

Add a bounded compilation queue or worker pool, deadline, and process cleanup on timeout/cancellation. Consider caching only with a key covering source data, settings, and template versions; mutable financial reports need explicit freshness rules. Profile synchronous template/file work before offloading it.

Validation: simultaneous exports, stalled compiler, cancellation, process cleanup, and equivalent generated documents.

## Suggested sequence and measurements

1. Address mail pacing/claim safety and Android's final delay; restore stats timings.
2. Establish a representative isolated baseline using the existing festival simulator. Include peak sales, online topups, dashboard polling, queued mail, and reports together.
3. Batch sale reads/writes and scope pending-topup lookups; compare query counts and tail latency.
4. Refactor payment/mail worker boundaries with concurrency and recovery tests before raising parallelism.
5. Measure route splitting and report limits independently.

Track sale p50/p95/p99, successful orders per second, database calls per sale, pool wait, account lock wait, serialization/deadlock rate, pending-payment age, mail queue age, dashboard query time, Android failure feedback, and web initial JavaScript size. Correct balances, tax snapshots, tenant isolation, and duplicate-booking prevention are acceptance gates for every throughput change.

Repository surface/check scripts map the main candidates to backend, administration web, and Android. Implementations require `make verify-backend`, `make verify-web-administration`, and/or `make verify-android` according to the touched surface, plus browser/device checks. Customer portal route changes require `make verify-web-customerportal`. Shared web-library changes require both web checks. Contract sync is unnecessary for internal-only changes, but must be reassessed if endpoint schemas change.

Investigation validation: reviewed source and migrations, checked surrounding existing optimizations and tests, ran surface/check mapping, and reproduced the mail timedelta conversion. No application test suite or benchmark was run because this investigation changes documentation only.

## Implementation and validation record — 2026-10-02

Implemented locally:

- Mail workers claim one message immediately before sending and drain the queue without adding the idle polling delay between deliveries. Claims return the updated row and load attachments only for that message.
- The configured 50 ms mail pacing now uses fractional seconds correctly. SMTP work runs outside database transactions, has a 60-second overall deadline, and records success/failure in separate short transactions. Cancellation propagates and leaves the processing lease for recovery. Delivery remains at-least-once: a crash after SMTP acceptance and before acknowledgement can still cause another delivery.
- Sales resolve button bundles and direct products in at most two queries, reconstructing repeated input positions and retaining scope, price, and returnability checks. Line-item inserts use one batched database operation. Ledger booking functions, balance updates, and tax snapshots remain unchanged.
- Android publishes final payment submission failures immediately after the HTTP layer finishes its attempts, removing the redundant one-second wait and the single-iteration retry loop.
- Statistics queries log elapsed duration and scope at DEBUG level, including failed queries. Enable that logger when collecting timings; this does not introduce a metrics backend.
- Administration dashboard polling pauses in hidden tabs and refreshes when focus returns. A timer scheduled before hiding may finish one poll before subsequent polls pause.

Validation:

| Check | Result |
| --- | --- |
| Focused backend regression suite on final code | 36 passed: mail claims/pacing, delivery success/failure/timeout/cancellation, pool release during SMTP, sales and statistics |
| Full backend suite | 349 passed; existing `test_sumup_auth_code_flow_saves_link_on_non_event_node` failed, matching the previous validation log. Final mail claim/deadline changes were subsequently covered by the focused suite. |
| Backend Ruff | Passed |
| Pylint on changed backend files | Passed |
| Repository backend lint | Existing payout-reminder missing `conn` argument and protected-access warning prevent a clean result |
| Repository MyPy | 29 existing errors in accounting-report and payout-reminder tests; no errors reported in changed files |
| Administration Jest suite | 108 passed, including actual RTK Query polling with browser visibility/focus events in jsdom |
| Administration production build | Passed |
| ESLint on changed administration files | Passed |
| Full administration lint target | Failed on existing issues; changed files pass separately |
| Android `assembleDebug`, `testDebugUnitTest`, `lintDebug` | Passed |
| Diff whitespace check | Passed |

The isolated local test database container was started for validation and restored to its original stopped state. Validation used its test database on port 5434. No production data was accessed, no deployment was performed, and no API/schema/generated-client or configuration changes are required.

Manual checks still pending: verify hidden-tab polling on an authenticated dashboard in a real browser; verify immediate failure feedback and manual retry on a physical terminal. Automated coverage includes browser events in jsdom and Android unit tests, but is not a substitute for those device checks. No throughput or tail-latency benchmark has been performed.

Remaining candidates after the first batch: payment-worker transaction boundaries and provider connection reuse, customer-scoped/indexed pending-topup lookup, fleet retry jitter, route-level loading, and PDF compiler resource limits. The second batch below addresses several of these.

## Second implementation batch — 2026-10-02

Implemented locally:

- Pending online topups are filtered by customer and payment method in SQL and limited to the newest eligible order. Shared, booked, and other customers' orders are excluded. The database codec stores these payloads as JSON strings containing JSON; the filter unwraps that representation before extracting fields.
- Migration `0000058` adds a partial customer/date index for pending online topups. Backend revision checks now expect this migration. Run the normal database migration step before starting the updated backend; index creation uses the standard transactional migration mechanism.
- The background payment worker resolves merchant settings in a short database transaction, releases the connection before OAuth renewal and checkout status requests, then re-reads and locks the pending row for booking. Complete transaction retries replace retries inside an already failed transaction. The same booking lock is used by terminal-triggered checks. Provider processing remains sequential; this change does not add parallel workers or claiming leases.
- PDF report generation runs at most two compilers per service process, with a 120-second compilation deadline. Timeout and cancellation terminate the compiler process group on supported Unix hosts and reap the process before removing temporary files. Queued work creates no subprocess until a slot is available.
- Android configuration fetch retries use bounded exponential backoff with jitter: initially 0.5–1 second and eventually 16–32 seconds. Explicit one-shot fetches and successful configuration handling retain their existing behavior.
- Administration statistics, reports, DSFinV-K export, device management, and help screens load asynchronously through separate route bundles. Existing access guards and loading/error boundaries remain in place. Total initial JavaScript still warrants further measurement; no percentage speedup is claimed.

No public API or generated-client changes are required. Separate sidebar changes appeared in the shared checkout during this work and were left untouched; web checks cover the combined checkout.

Outstanding follow-up: provider HTTP connection reuse, limits/claims for large payment queues, transaction boundaries in interactive checkout creation, and a representative combined-load benchmark. HTTP-layer Android retries still use their existing schedule; this batch changes configuration-level retries. Verify new route navigation/loading in an authenticated browser and prolonged configuration recovery on a physical terminal before deployment.

Second-batch validation:

- Full backend suite on final behavior: 359 passed, with only the previously known `test_sumup_auth_code_flow_saves_link_on_non_event_node` failure. New coverage verifies scoped/shared-order lookup, migration presence, single booking under concurrent reconciliation, transaction retry, connection release during checkout/OAuth requests, compiler concurrency, timeout, and cancellation cleanup.
- Administration: 111 tests passed and a fresh production build passed. Router ESLint passed. The full administration lint target still fails on existing issues.
- Android: debug build, unit tests, and lint passed, including bounded backoff/jitter coverage.
- Backend Ruff and Pylint on changed files passed. Repository lint still fails on the existing payout-reminder issues; MyPy still reports the same 29 errors in two existing test files, with none in changed files. Existing formatting differences outside the edited portions of backend files were preserved.
- Diff whitespace check passed. No public API or generated artifacts changed. The isolated test database was returned to its original stopped state after validation.

Changes are local and have not been deployed. Migration `0000058` and the real-browser/device checks described above remain deployment follow-up requirements.
