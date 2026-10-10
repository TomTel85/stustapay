"""Protect the shared test ledger against false positives from duplicate booking."""

import unittest
from copy import deepcopy

from tools.offline_emulator_server import EmulatorCoordinator


class SharedLedgerTest(unittest.TestCase):
    def setUp(self):
        self.coordinator = EmulatorCoordinator()
        self.coordinator.scenario("test", 700)
        for terminal in (1, 2, 3):
            self.coordinator.prepare(
                "test",
                terminal,
                {
                    "id": f"snapshot-{terminal}",
                    "terminal_id": terminal,
                    "till_id": terminal,
                    "customers": [{"balance_cents": 700}],
                },
            )

    @staticmethod
    def booking(terminal, quantity=1, button=1, order_uuid=None):
        return {
            "snapshot_id": f"snapshot-{terminal}",
            "sequence": 1,
            "recorded_at": "timestamp",
            "sale": {
                "uuid": order_uuid or f"sale-{terminal}",
                "payment_method": "tag",
                "customer_tag_uid": "42",
                "used_vouchers": "0",
                "buttons": [{"till_button_id": str(button), "quantity": str(quantity)}],
            },
        }

    def test_separate_snapshots_share_balance_and_allow_overdraft(self):
        for terminal in (3, 1, 2):
            result = self.coordinator.import_bookings("test", terminal, [self.booking(terminal)])[0]
            self.assertEqual(result["status"], "booked")
        state = self.coordinator.scenarios["test"]
        self.assertEqual(state["balance_cents"], -800)
        self.assertEqual(len(state["orders"]), 3)

    def test_lost_reply_replay_keeps_original_receipt_and_balance(self):
        booking = self.booking(1)
        original = self.coordinator.import_bookings("test", 1, [booking])[0]
        replay = self.coordinator.import_bookings("test", 1, [booking])[0]
        self.assertEqual(replay, {**original, "status": "already_booked"})
        self.assertEqual(self.coordinator.scenarios["test"]["balance_cents"], 200)
        self.assertEqual(len(self.coordinator.scenarios["test"]["orders"]), 1)

    def test_conflicting_uuid_and_sequence_cannot_debit_again(self):
        booking = self.booking(1)
        self.coordinator.import_bookings("test", 1, [booking])
        conflicting = deepcopy(booking)
        conflicting["sale"]["buttons"][0]["quantity"] = "2"
        result = self.coordinator.import_bookings("test", 1, [conflicting])[0]
        self.assertEqual(result["status"], "clarification_required")
        conflicting["sale"]["uuid"] = "another-sale"
        result = self.coordinator.import_bookings("test", 1, [conflicting])[0]
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(self.coordinator.scenarios["test"]["balance_cents"], 200)

    def test_wrong_terminal_cannot_import_another_snapshot(self):
        result = self.coordinator.import_bookings("test", 2, [self.booking(1)])[0]
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(self.coordinator.scenarios["test"]["balance_cents"], 700)

    def test_deposit_return_credits_once(self):
        booking = self.booking(1, quantity=-2, button=2)
        self.coordinator.import_bookings("test", 1, [booking])
        self.coordinator.import_bookings("test", 1, [booking])
        self.assertEqual(self.coordinator.scenarios["test"]["balance_cents"], 1100)


if __name__ == "__main__":
    unittest.main()
