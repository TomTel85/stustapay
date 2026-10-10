# Offline sales on multiple Android emulators

Run the coordinated suite with three separate Android emulator processes:

```sh
make test-offline-emulators
```

The runner builds the debug app and instrumentation APKs, starts three isolated instances of the existing `Medium_Phone_API_35` AVD, and connects them to a shared test server on the host through `adb reverse`. It uses a dedicated ADB daemon and excludes USB devices. Each instance has its own app process, Room database, terminal ID, till ID, and offline preparation. The test supplies wristband UID `42` directly to the sale model, so it needs no NFC reader or physical wristband.

The runner also executes the existing offline repository, journal persistence, and journal UI instrumentation tests on every emulator. It checks both the device test results and the shared server ledger, including exact booking IDs, account balances, independent sequence numbers, and duplicate imports.

## Coordinated scenarios

| Scenario | Assertions |
| --- | --- |
| Shared spending during an outage | All devices prepare the same €7 balance and independently accept a €5 sale. Further spending on the same device, unknown tags, and vouchers are blocked. Devices reconnect in reverse order; the shared account can become negative, and each sale books once. |
| Lost reply and app process restart | The test server commits each import, but the client receives a transport error. Every app process is stopped and restarted with its existing journal. Stored payloads and sequences stay unchanged, and replay confirms the original bookings without another debit. |
| Temporary failure and separate reconnection | Each device accepts two sales. A retry-required response keeps both pending. Devices reconnect separately, including an app process restart for the last device. All original bookings eventually settle. |
| Deposit credits | A locally accepted deposit return cannot fund another offline purchase. The return and permitted purchase settle against the shared account when connectivity is restored. |
| Storage, expiry, and revocation | Low storage blocks new sales while accepted-sale replay and synchronization still work. Expired or revoked preparation blocks new offline acceptance. |
| Transaction and customer limits | Sufficient funds do not bypass the €20 transaction or €30 per-customer limit. Purchases reaching the exact limit are accepted. |
| Till limits | A €15 till budget is enforced independently of the customer limit, and its exact remaining amount is usable. |

## Configuration and results

Use two to six emulator instances:

```sh
make test-offline-emulators OFFLINE_EMULATOR_DEVICES=4
```

Specify another installed AVD or SDK location:

```sh
python3 tools/test_offline_emulators.py --devices 3 --avd YOUR_AVD --sdk /path/to/Android/sdk
```

`--skip-build` reuses the current debug APKs. The runner requires Python 3.11, the Android SDK emulator and platform tools, an installed AVD/system image, and enough memory to boot all devices together. The default is 1.5 GiB of guest RAM per device. See available profiles with `emulator -list-avds`.

Logs and `results.json` are written to `app/build/reports/offline-emulators/<run timestamp>/`. A run returns a failing exit code if a scenario assertion, emulator boot, app test, or installation fails. Instances started by the runner are stopped after the run. Existing connected devices are not selected for installation or testing. Read-only AVD instances keep the saved profile's userdata unchanged.

## What the suite exercises

This is Android repository and Room integration coverage across actual emulator processes. Sales use a controlled `OfflineSalesTransport` and a deterministic shared test ledger. Connectivity faults are injected at the sales transport; the coordinator connection stays available to drive the tests. Process recovery is tested with app force-stop and a new instrumentation process, rather than a device reboot.

The test ledger models shared balances and idempotent imports; it does not replace the backend accounting tests. Run those against the configured test database:

```sh
python3 -m pytest stustapay/tests/terminal/test_offline.py \
  stustapay/tests/terminal/test_offline_reconciliation.py \
  stustapay/tests/terminal/test_offline_two_terminals.py
```

Real NFC scanning, actual radio/network outages, background connectivity callbacks, customer-display hardware, receipts, and TSE still need the physical-device pilot described in `offline-sales-operations.md`. The suite injects tag UIDs only inside the instrumentation APK; the production scan flow has no bypass.

The coordinator's own ledger checks can be run without an Android SDK:

```sh
python3 -m unittest discover -s tools/tests -p test_offline_emulator_server.py
```
