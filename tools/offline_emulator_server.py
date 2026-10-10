"""Loopback-only coordinator and deterministic shared ledger for Android emulator tests.

This models transport and shared-account effects. Backend accounting, authorization,
and TSE correctness remain covered by the real backend integration tests.
"""

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Condition
from time import monotonic
from uuid import uuid4


class EmulatorCoordinator:
    def __init__(self):
        self.condition = Condition()
        self.ready = set()
        self.commands = defaultdict(deque)
        self.results = {}
        self.scenarios = {}

    def scenario(self, name: str, balance_cents: int):
        with self.condition:
            if name in self.scenarios:
                raise ValueError(f"Scenario already exists: {name}")
            self.scenarios[name] = {
                "initial_balance_cents": balance_cents,
                "balance_cents": balance_cents,
                "snapshots": {},
                "orders": {},
                "sequences": {},
                "duplicate_imports": 0,
            }

    def prepare(self, name: str, terminal: int, snapshot: dict):
        state = self.scenarios[name]
        if snapshot["terminal_id"] != terminal or snapshot["till_id"] != terminal:
            raise ValueError("Snapshot belongs to another terminal")
        # Another emulator may import between reading the balance and registering this snapshot.
        # Keep the captured historical value, just as disconnected clients do.
        state["snapshots"][snapshot["id"]] = snapshot

    def import_bookings(self, name: str, terminal: int, bookings: list[dict]) -> list[dict]:
        state = self.scenarios[name]
        results = []
        for booking in bookings:
            sale = booking["sale"]
            order_uuid = sale["uuid"]
            snapshot = state["snapshots"].get(booking["snapshot_id"])
            existing = state["orders"].get(order_uuid)
            if existing:
                if existing["booking"] != booking or existing["terminal"] != terminal:
                    results.append({"uuid": order_uuid, "status": "clarification_required", "message": "UUID conflict"})
                else:
                    state["duplicate_imports"] += 1
                    results.append({**existing["receipt"], "status": "already_booked"})
                continue
            sequence = (booking["snapshot_id"], booking["sequence"])
            if snapshot is None or snapshot["terminal_id"] != terminal or sequence in state["sequences"]:
                results.append(
                    {"uuid": order_uuid, "status": "clarification_required", "message": "Snapshot/sequence conflict"}
                )
                continue
            if (
                sale["payment_method"] != "tag"
                or int(sale["customer_tag_uid"]) != 42
                or int(sale.get("used_vouchers") or 0)
            ):
                raise ValueError("Unexpected sale type in test ledger")
            amount = 0
            for button in sale["buttons"]:
                button_id = int(button["till_button_id"])
                quantity = int(button["quantity"])
                if button_id not in (1, 2) or (button_id == 1 and quantity < 0):
                    raise ValueError("Unsupported test product")
                amount += (500 if button_id == 1 else 200) * quantity
            old_balance = state["balance_cents"]
            state["balance_cents"] -= amount
            receipt = {
                "uuid": order_uuid,
                "status": "booked",
                "old_balance_cents": old_balance,
                "new_balance_cents": state["balance_cents"],
                "order_id": len(state["orders"]) + 1,
                "booked_at": datetime.now(timezone.utc).isoformat(),
                "snapshot": snapshot,
                "sale": sale,
            }
            state["orders"][order_uuid] = {"receipt": receipt, "booking": booking, "terminal": terminal}
            state["sequences"][sequence] = order_uuid
            results.append(receipt)
        return results

    def enqueue(self, terminal: int, operation: str, **arguments) -> str:
        with self.condition:
            command_id = str(uuid4())
            self.commands[terminal].append({"id": command_id, "operation": operation, **arguments})
            self.condition.notify_all()
            return command_id

    def wait_ready(self, terminals: list[int], timeout: float = 120):
        deadline = monotonic() + timeout
        with self.condition:
            while not set(terminals).issubset(self.ready):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Emulators not ready: {set(terminals) - self.ready}")
                self.condition.wait(remaining)

    def wait_results(self, commands: dict[int, str], timeout: float = 30) -> dict[int, dict]:
        deadline = monotonic() + timeout
        with self.condition:
            while any(command_id not in self.results for command_id in commands.values()):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Emulator commands timed out: {commands}")
                self.condition.wait(remaining)
            results = {terminal: self.results.pop(command_id) for terminal, command_id in commands.items()}
        for terminal, result in results.items():
            if not result["ok"]:
                raise RuntimeError(f"Emulator {terminal} failed:\n{result['error']}")
        return {terminal: result["state"] for terminal, result in results.items()}

    def dispatch(self, path: str, payload: dict | None) -> dict:
        parts = path.strip("/").split("/")
        with self.condition:
            action = parts[0]
            if action == "ready":
                self.ready.add(int(parts[1]))
                self.condition.notify_all()
                return {}
            if action == "command":
                queue = self.commands[int(parts[1])]
                return queue.popleft() if queue else {}
            if action == "result":
                self.results[payload["id"]] = payload
                self.condition.notify_all()
                return {}
            state = self.scenarios[parts[1]]
            if action == "balance":
                return {"balance_cents": state["balance_cents"]}
            if action == "prepare":
                self.prepare(parts[1], int(parts[2]), payload)
                return {}
            if action == "import":
                return {"results": self.import_bookings(parts[1], int(parts[2]), payload["bookings"])}
            if action == "status":
                order = state["orders"].get(parts[2])
                return order["receipt"] if order else {"status": "not_found"}
            raise ValueError(f"Unknown coordinator path: {path}")


def create_server(coordinator: EmulatorCoordinator, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            pass

        def handle_request(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    raise ValueError("Coordinator payload too large")
                payload = json.loads(self.rfile.read(length)) if length else None
                response = coordinator.dispatch(self.path, payload)
                status = 200
            except (KeyError, ValueError, TypeError) as error:
                response, status = {"error": str(error)}, 400
            body = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
