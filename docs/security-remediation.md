# Security remediation — 2 October 2026

This review covered authentication and authorization paths, customer payment ownership checks,
image uploads, XML processing, dynamic SQL, template rendering, Android transport configuration,
and declared Python, web, and Android dependencies. It does not establish that every possible
security issue has been eliminated or assess a running production deployment.

## Fixes

- Updated Axios, brace-expansion, fast-uri, and Undici overrides and regenerated the web lockfile.
  The initial npm audit reported 17 affected packages; the final audit reports zero.
  These include the published [brace-expansion denial-of-service advisory](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr),
  [fast-uri normalization advisory](https://github.com/advisories/GHSA-hrr3-gc8f-f4qj), and
  [Undici response-splitting advisory](https://github.com/advisories/GHSA-r53p-7pc4-xj5r).
- Reject malformed, oversized, and deeply nested JWT input through the authentication error path.
  Reject non-finite and boolean timestamp claims; expiration at the current time is expired.
- Reject passwords that bcrypt cannot represent faithfully: empty values, null characters, and
  passwords longer than 72 UTF-8 bytes. Accounts without a password hash fail authentication cleanly.
- Revoke administration sessions and pending invitations when a password is changed or reset,
  including invitation acceptance. The administration app clears saved authentication after
  changing its own user's password, and clears cached API data when credentials change so that
  a new login cannot reuse a previous account's cached data.
- Serialize login, password changes, and invitation acceptance with database row locks. An
  invitation can be consumed once, and an old-password login cannot create a surviving session
  after password revocation. Missing password-reset targets are now detected correctly.
- Limit banner decoding to 16 million pixels as well as the existing 5 MiB byte limit. Handle
  decompression-bomb errors and serve unsafe stored payloads as attachments with `nosniff`.
- Use defusedxml for DSFinV-K index validation, rejecting XML entity expansion.

## Validation

- Final npm audit: zero reported vulnerabilities in the locked dependency graph.
- Python dependency audit: zero reported vulnerabilities in the resolved declared runtime and
  build dependencies, including the new defusedxml dependency.
- OSV check: no advisories returned for 35 directly declared Android Maven coordinates.
  Android transitive dependencies and the bundled Headwind AAR were not comprehensively audited.
- Focused backend security tests: 75 passed, including concurrent invitation acceptance.
- Administration web tests: 107 passed; customer portal web tests: 34 passed.
- Both production web builds passed. Customer portal lint passed.
- Ruff passed. Pylint passed for changed Python files; no changed-file MyPy errors remain.

The final full backend suite had 342 passing tests and one unrelated failure. Repository
lint/type checks also expose unrelated existing failures:
SumUp link upsert uses an `ON CONFLICT` target incompatible with the current schema;
administration lint reports seven errors in existing MDM, revenue-chart, and cash-register code;
backend Pylint reports a missing database argument and protected-member warnings in payout reminder
code; MyPy reports 29 errors in accounting-report and payout-reminder tests.

Static scanner SQL findings were reviewed as parameterized values with internally selected
columns, table names, and SQL fragments. Its Jinja HTML-escaping warning concerns LaTeX templates,
whose text inputs use LaTeX escaping; its Markup warning concerns already-rendered email HTML.
Simulator passwords and pseudo-random values are test hardware data.

## Rollout behavior

Install the updated Python and locked web dependencies when deploying these changes. No database
migration or API/client regeneration is required. Password changes sign out all existing
administration sessions and invalidate outstanding invitations. Existing passwords longer than
72 UTF-8 bytes require an administrator reset. Existing large banners may be served as downloads.
Authenticated browser password-change QA remains a manual follow-up; reducer behavior is covered
by web regression tests. These changes have not been deployed.
