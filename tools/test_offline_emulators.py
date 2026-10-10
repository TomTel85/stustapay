#!/usr/bin/env python3
"""Run coordinated NFC-free offline sales on several actual Android emulator processes."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from uuid import uuid4

from offline_emulator_server import EmulatorCoordinator, create_server

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "de.teamfestlichpay.teamfestlichpay.debug"
RUNNER = f"{PACKAGE}.test/androidx.test.runner.AndroidJUnitRunner"
COORDINATED_TEST = "de.stustapay.stustapay.offline.MultiDeviceOfflineSalesTest"
LOCAL_TESTS = ",".join(
    (
        "de.stustapay.stustapay.offline.AutonomousSalesRepositoryTest",
        "de.stustapay.stustapay.offline.SalesJournalPersistenceTest",
        "de.stustapay.stustapay.ui.OfflineJournalUiTest",
    )
)


def run(command: list[str], timeout=90, cwd=ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


class Emulator:
    def __init__(self, terminal: int, port: int, sdk: Path, avd: str, output: Path, adb_port: int):
        self.terminal = terminal
        self.serial = f"emulator-{port}"
        self.adb = str(sdk / "platform-tools" / "adb")
        self.adb_port = adb_port
        self.output = output
        self.log = (output / f"emulator-{terminal}.log").open("w", encoding="utf-8")
        # Read-only instances isolate userdata and avoid modifying the user's saved AVD.
        environment = os.environ.copy()
        environment["ANDROID_ADB_SERVER_PORT"] = str(adb_port)
        environment["ADB_SERVER_SOCKET"] = f"tcp:127.0.0.1:{adb_port}"
        self.process = subprocess.Popen(
            [
                str(sdk / "emulator" / "emulator"),
                "-avd",
                avd,
                "-port",
                str(port),
                "-read-only",
                "-no-window",
                "-no-audio",
                "-no-snapshot",
                "-no-boot-anim",
                "-no-direct-adb",
                "-memory",
                "1536",
                "-cores",
                "2",
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        self.test = None
        self.test_log = None
        self.test_path = None
        self.phase = 0

    def command(self, *args: str, timeout=90) -> str:
        return run([self.adb, "-P", str(self.adb_port), "-s", self.serial, *args], timeout=timeout)

    def install(self, coordinator_port: int):
        self.command("install", "--no-streaming", "-r", str(ROOT / "app/app/build/outputs/apk/debug/app-debug.apk"))
        self.command(
            "install",
            "--no-streaming",
            "-t",
            "-r",
            str(ROOT / "app/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"),
        )
        if self.command("shell", "pm", "clear", PACKAGE).strip() != "Success":
            raise RuntimeError(f"Could not clear the disposable test app on {self.serial}")
        self.command("reverse", f"tcp:{coordinator_port}", f"tcp:{coordinator_port}")

    def instrumentation(self, class_name: str, arguments: dict[str, str]):
        self.phase += 1
        self.test_path = self.output / f"instrumentation-{self.terminal}-{self.phase}.log"
        self.test_log = self.test_path.open("w", encoding="utf-8")
        command = [
            self.adb,
            "-P",
            str(self.adb_port),
            "-s",
            self.serial,
            "shell",
            "am",
            "instrument",
            "-w",
            "-r",
            "-e",
            "class",
            class_name,
        ]
        for key, value in arguments.items():
            command.extend(("-e", key, str(value)))
        command.append(RUNNER)
        self.test = subprocess.Popen(command, stdout=self.test_log, stderr=subprocess.STDOUT)

    def start_coordinated(self, coordinator_port: int, state: dict | None = None):
        arguments = {
            "offlineCoordinator": f"http://127.0.0.1:{coordinator_port}",
            "offlineTerminal": str(self.terminal),
        }
        if state:
            arguments.update(offlineDatabase=state["database"], offlineScenario=state["scenario"])
        self.instrumentation(COORDINATED_TEST, arguments)

    def wait_test(self) -> int:
        self.test.wait(timeout=45)
        self.test_log.close()
        output = self.test_path.read_text(encoding="utf-8")
        match = re.search(r"OK \((\d+) tests?\)", output)
        if self.test.returncode or not match:
            raise RuntimeError(f"Instrumentation failed on {self.serial}:\n{output}")
        return int(match.group(1))

    def stop(self):
        if self.test is not None and self.test.poll() is None:
            try:
                self.command("shell", "am", "force-stop", PACKAGE, timeout=10)
                self.test.wait(timeout=10)
            except (RuntimeError, subprocess.TimeoutExpired):
                self.test.terminate()
        if self.test_log is not None and not self.test_log.closed:
            self.test_log.close()
        if self.process.poll() is None:
            try:
                self.command("emu", "kill", timeout=10)
                self.process.wait(timeout=15)
            except (RuntimeError, subprocess.TimeoutExpired):
                self.process.terminate()
        self.log.close()


def free_ports(adb: str, count: int, adb_port: int) -> list[int]:
    inventory = run([adb, "-P", str(adb_port), "devices"])
    ports = []
    for port in range(5560, 5680, 2):
        if f"emulator-{port}" in inventory:
            continue
        try:
            with socket.socket() as console, socket.socket() as bridge:
                console.bind(("127.0.0.1", port))
                bridge.bind(("127.0.0.1", port + 1))
        except OSError:
            continue
        ports.append(port)
        if len(ports) == count:
            return ports
    raise RuntimeError("Not enough unused emulator ports")


def free_adb_port() -> int:
    for port in range(5038, 5058):
        try:
            with socket.socket() as connection:
                connection.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise RuntimeError("No unused ADB test server port")


def wait_boot(devices: list[Emulator]):
    deadline = time.monotonic() + 180
    waiting = devices.copy()
    last_update = 0
    while waiting:
        for device in waiting.copy():
            if device.process.poll() is not None:
                raise RuntimeError(
                    f"Emulator exited: {device.serial}; inspect {device.output}/emulator-{device.terminal}.log"
                )
            try:
                if device.command("shell", "getprop", "sys.boot_completed", timeout=5).strip() == "1":
                    waiting.remove(device)
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"Emulator boot timed out: {[device.serial for device in waiting]}")
        if waiting and time.monotonic() - last_update >= 15:
            print(f"Waiting for Android boot: {', '.join(device.serial for device in waiting)}", flush=True)
            last_update = time.monotonic()
        if waiting:
            time.sleep(1)


class Scenarios:
    def __init__(self, coordinator: EmulatorCoordinator, devices: list[Emulator], port: int):
        self.coordinator = coordinator
        self.devices = {device.terminal: device for device in devices}
        self.ids = list(self.devices)
        self.port = port
        self.report = []

    def send(self, ids: list[int], operation: str, **arguments) -> dict[int, dict]:
        commands = {terminal: self.coordinator.enqueue(terminal, operation, **arguments) for terminal in ids}
        return self.coordinator.wait_results(commands)

    def reset(self, name: str, balance: int):
        self.coordinator.scenario(name, balance)
        self.send(self.ids, "reset", scenario=name)

    def sales(self, accepted=True, **arguments) -> tuple[dict[int, str], dict[int, dict]]:
        uuids = {terminal: str(uuid4()) for terminal in self.ids}
        commands = {
            terminal: self.coordinator.enqueue(terminal, "sale", uuid=uuids[terminal], accepted=accepted, **arguments)
            for terminal in self.ids
        }
        return uuids, self.coordinator.wait_results(commands)

    @staticmethod
    def rows(states: dict[int, dict], state: str, count: int):
        for terminal, result in states.items():
            rows = result["rows"]
            if len(rows) != count or any(row["state"] != state for row in rows):
                raise AssertionError(f"Terminal {terminal}: expected {count} {state} rows, received {rows}")

    def replay(self, uuids: dict[int, str]):
        commands = {
            terminal: self.coordinator.enqueue(terminal, "replay", uuid=value) for terminal, value in uuids.items()
        }
        self.coordinator.wait_results(commands)

    def restart(self, ids: list[int]) -> dict[int, dict]:
        before = self.send(ids, "pause")
        for terminal in ids:
            device = self.devices[terminal]
            device.wait_test()
            device.command("shell", "am", "force-stop", PACKAGE)
        with self.coordinator.condition:
            self.coordinator.ready.difference_update(ids)
        for terminal in ids:
            self.devices[terminal].start_coordinated(self.port, before[terminal])
        self.coordinator.wait_ready(ids)
        after = self.send(ids, "state")
        for terminal in ids:
            if before[terminal]["rows"] != after[terminal]["rows"]:
                raise AssertionError(f"Process restart changed the stored journal on terminal {terminal}")
        return after

    def record(self, name: str, orders: int, balance: int, expected_uuids: set[str], duplicates: int = 0):
        state = self.coordinator.scenarios[name]
        if len(state["orders"]) != orders or state["balance_cents"] != balance:
            raise AssertionError(
                f"{name}: unexpected ledger totals ({len(state['orders'])} orders, {state['balance_cents']} cents)"
            )
        if set(state["orders"]) != expected_uuids or state["duplicate_imports"] != duplicates:
            raise AssertionError(f"{name}: UUID or replay mismatch")
        if {order["terminal"] for order in state["orders"].values()} != set(self.ids):
            raise AssertionError(f"{name}: missing emulator imports")
        self.report.append(
            {
                "scenario": name,
                "devices": len(self.ids),
                "orders": orders,
                "balance_cents": balance,
                "duplicate_imports": duplicates,
                "passed": True,
            }
        )
        print(f"PASS {name}: {orders} distinct bookings, shared balance {balance / 100:.2f}", flush=True)

    def run(self):
        count = len(self.ids)

        self.reset("shared-spending", 700)
        self.send(self.ids, "network", online=False)
        sales, states = self.sales()
        self.rows(states, "offline", 1)
        if any(state["foreground_requests"] for state in states.values()):
            raise AssertionError("Local acceptance made a foreground network request")
        _, states = self.sales(accepted=False)  # Same cached funds cannot be spent twice on one device.
        self.rows(states, "offline", 1)
        self.sales(accepted=False, tag=99)
        self.sales(accepted=False, vouchers=1)
        self.send(self.ids, "synchronize", success=False)
        if self.coordinator.scenarios["shared-spending"]["orders"]:
            raise AssertionError("Disconnected devices reached the server")
        for terminal in reversed(self.ids):
            self.send([terminal], "network", online=True)
            self.rows(self.send([terminal], "synchronize", success=True), "booked", 1)
        self.replay(sales)
        self.send(self.ids, "synchronize", success=True)
        self.record("shared-spending", count, 700 - 500 * count, set(sales.values()))

        self.reset("lost-reply-and-process-restart", 2000)
        self.send(self.ids, "network", online=False)
        sales, _ = self.sales()
        self.send(self.ids, "network", online=True, lose_reply_once=True)
        self.rows(self.send(self.ids, "synchronize", success=False), "offline", 1)
        if len(self.coordinator.scenarios["lost-reply-and-process-restart"]["orders"]) != count:
            raise AssertionError("Lost-reply fault did not happen after the server commit")
        self.rows(self.restart(self.ids), "offline", 1)
        self.rows(self.send(self.ids, "synchronize", success=True), "booked", 1)
        self.replay(sales)
        self.send(self.ids, "synchronize", success=True)
        self.record("lost-reply-and-process-restart", count, 2000 - 500 * count, set(sales.values()), duplicates=count)

        self.reset("temporary-failure-and-separate-reconnect", 2000)
        self.send(self.ids, "network", online=False)
        first, _ = self.sales()
        second, states = self.sales()
        self.rows(states, "offline", 2)
        if any(sorted(row["sequence"] for row in state["rows"]) != [1, 2] for state in states.values()):
            raise AssertionError("Journal sequences were not independent and monotonic")
        self.send(self.ids, "network", online=True, retry_required=True)
        self.rows(self.send(self.ids, "synchronize", success=False), "offline", 2)
        if self.coordinator.scenarios["temporary-failure-and-separate-reconnect"]["orders"]:
            raise AssertionError("A retry-required response booked a sale")
        self.send([self.ids[0]], "network", online=False)
        self.send(self.ids[1:], "network", online=True)
        self.rows(self.send(self.ids[1:], "synchronize", success=True), "booked", 2)
        self.rows(self.send([self.ids[0]], "synchronize", success=False), "offline", 2)
        self.rows(self.restart([self.ids[0]]), "offline", 2)
        self.rows(self.send([self.ids[0]], "synchronize", success=True), "booked", 2)
        self.record(
            "temporary-failure-and-separate-reconnect",
            2 * count,
            2000 - 1000 * count,
            set(first.values()) | set(second.values()),
        )

        self.reset("deposit-credit-is-not-local-spending-money", 700)
        self.send(self.ids, "network", online=False)
        returns, _ = self.sales(button=2, quantity=-2)
        self.sales(accepted=False, quantity=2)
        sales, states = self.sales()
        self.rows(states, "offline", 2)
        if any(sum(row["debit_cents"] for row in state["rows"]) != 500 for state in states.values()):
            raise AssertionError("Unconfirmed return increased local spending balance")
        self.send(self.ids, "network", online=True)
        self.rows(self.send(self.ids, "synchronize", success=True), "booked", 2)
        self.record(
            "deposit-credit-is-not-local-spending-money",
            2 * count,
            700 - 100 * count,
            set(returns.values()) | set(sales.values()),
        )

        self.reset("storage-expiry-and-revocation", 2000)
        self.send(self.ids, "network", online=False)
        sales, _ = self.sales()
        self.send(self.ids, "storage", bytes=0)
        self.sales(accepted=False)
        self.replay(sales)
        self.send(self.ids, "network", online=True)
        self.rows(self.send(self.ids, "synchronize", success=True), "booked", 1)
        self.send(self.ids, "storage", bytes=2**63 - 1)
        self.send(self.ids, "network", online=False)
        self.send(self.ids, "expire")
        self.sales(accepted=False)
        self.send(self.ids, "network", online=True)
        self.send(self.ids, "synchronize", success=True)
        self.send(self.ids, "network", online=False)
        self.send(self.ids, "revoke")
        self.sales(accepted=False)
        self.record("storage-expiry-and-revocation", count, 2000 - 500 * count, set(sales.values()))

        self.reset("transaction-and-customer-limits", 5000)
        self.send(self.ids, "network", online=False)
        self.sales(accepted=False, quantity=5)  # €25 exceeds the €20 transaction ceiling despite enough funds.
        first, _ = self.sales(quantity=4)
        self.sales(accepted=False, quantity=3)  # €20 + €15 exceeds the €30 customer ceiling.
        second, states = self.sales(quantity=2)  # The exact customer limit remains usable.
        self.rows(states, "offline", 2)
        self.sales(accepted=False)
        self.send(self.ids, "network", online=True)
        self.rows(self.send(self.ids, "synchronize", success=True), "booked", 2)
        self.record(
            "transaction-and-customer-limits",
            2 * count,
            5000 - 3000 * count,
            set(first.values()) | set(second.values()),
        )

        self.reset("till-limits", 5000)
        self.send(self.ids, "network", online=False)
        first, _ = self.sales(quantity=2)
        self.sales(
            accepted=False, quantity=2
        )  # €20 remains below the customer ceiling but exceeds this till's €15 cap.
        second, states = self.sales()  # The exact till ceiling is allowed.
        self.rows(states, "offline", 2)
        self.sales(accepted=False)
        self.send(self.ids, "network", online=True)
        self.rows(self.send(self.ids, "synchronize", success=True), "booked", 2)
        self.record("till-limits", 2 * count, 5000 - 1500 * count, set(first.values()) | set(second.values()))

        self.send(self.ids, "finish")
        for device in self.devices.values():
            device.wait_test()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", type=int, default=3, help="Number of separate emulator processes (2–6; default 3)")
    parser.add_argument(
        "--avd", default="Medium_Phone_API_35", help="Existing AVD cloned as isolated read-only instances"
    )
    parser.add_argument(
        "--sdk", type=Path, default=Path(os.environ.get("ANDROID_HOME", "~/Library/Android/sdk")).expanduser()
    )
    parser.add_argument("--skip-build", action="store_true", help="Reuse already built debug and instrumentation APKs")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "app/build/reports/offline-emulators" / datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    args = parser.parse_args()
    if not 2 <= args.devices <= 6:
        parser.error("--devices must be between 2 and 6")
    for binary in (args.sdk / "platform-tools/adb", args.sdk / "emulator/emulator"):
        if not binary.is_file():
            parser.error(f"SDK binary missing: {binary}")
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.skip_build:
        print("Building Android debug and instrumentation APKs…", flush=True)
        with (args.output / "gradle.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                ["./gradlew", ":app:assembleDebug", ":app:assembleDebugAndroidTest"],
                cwd=ROOT / "app",
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if result.returncode:
            print(f"Android build failed; inspect {args.output / 'gradle.log'}", file=sys.stderr)
            return 1
    for apk in ("debug/app-debug.apk", "androidTest/debug/app-debug-androidTest.apk"):
        if not (ROOT / "app/app/build/outputs/apk" / apk).is_file():
            parser.error(f"APK missing: {apk}; run without --skip-build")

    coordinator = EmulatorCoordinator()
    server = create_server(coordinator)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    devices = []
    adb = str(args.sdk / "platform-tools/adb")
    adb_port = free_adb_port()
    report = {"passed": False, "devices": args.devices, "scenarios": [], "local_instrumentation_tests": {}}
    try:
        # A dedicated daemon avoids shared-server interference and never opens a physical USB device.
        run([adb, "-P", str(adb_port), "--one-device", "offline-emulator-test-only", "start-server"])
        report["adb_server_port"] = adb_port
        ports = free_ports(adb, args.devices, adb_port)
        print(f"Launching {args.devices} isolated {args.avd} emulator processes…", flush=True)
        for terminal, port in enumerate(ports, start=1):
            devices.append(Emulator(terminal, port, args.sdk, args.avd, args.output, adb_port))
        report["emulators"] = [device.serial for device in devices]
        wait_boot(devices)
        # Serial uploads avoid saturating ADB while several emulators finish booting.
        for device in devices:
            print(f"Installing test APKs on {device.serial}…", flush=True)
            device.install(server.server_port)
        for device in devices:
            device.start_coordinated(server.server_port)
        coordinator.wait_ready([device.terminal for device in devices])
        print("All emulators ready; running seven coordinated scenarios…", flush=True)
        scenarios = Scenarios(coordinator, devices, server.server_port)
        report["scenarios"] = scenarios.report
        scenarios.run()
        print("Running the existing offline journal, repository, and UI tests on every emulator…", flush=True)
        for device in devices:
            device.instrumentation(LOCAL_TESTS, {})
        for device in devices:
            tests = device.wait_test()
            report["local_instrumentation_tests"][device.serial] = tests
            print(f"PASS {device.serial}: {tests} local instrumentation tests", flush=True)
        report["passed"] = True
    except (RuntimeError, TimeoutError, AssertionError, OSError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
        print(f"FAIL: {error}", file=sys.stderr, flush=True)
    finally:
        for device in devices:
            device.stop()
        try:
            run([adb, "-P", str(adb_port), "kill-server"], timeout=10)
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            pass
        server.shutdown()
        server.server_close()
        (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Results and emulator logs: {args.output}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
