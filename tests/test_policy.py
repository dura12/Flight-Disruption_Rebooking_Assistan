from __future__ import annotations

import unittest

from src.policy import evaluate_policy


class PolicyTests(unittest.TestCase):
    def test_rebook_rejects_cabin_upgrade(self):
        booking = {
            "cabin_class": "economy",
            "departure_datetime": "2026-10-03T10:00:00",
        }
        solution = {
            "type": "rebook",
            "flight": {
                "cabin_class": "business",
                "departure_datetime": "2026-10-03T16:00:00",
                "connection_minutes": None,
            },
        }
        ok, reason = evaluate_policy(booking, solution)
        self.assertFalse(ok)
        self.assertIn("Cabin upgrade", reason)

    def test_rebook_accepts_same_cabin_within_48h(self):
        booking = {
            "cabin_class": "economy",
            "departure_datetime": "2026-10-01T08:00:00",
        }
        solution = {
            "type": "rebook",
            "flight": {
                "cabin_class": "economy",
                "departure_datetime": "2026-10-01T22:00:00",
                "connection_minutes": None,
            },
        }
        ok, _ = evaluate_policy(booking, solution)
        self.assertTrue(ok)

    def test_refund_full_on_airline_cancel(self):
        booking = {
            "fare_amount": 650.0,
            "tax_amount": 85.0,
            "disruption_type": "cancelled",
            "fare_type": "flex",
        }
        ok, _ = evaluate_policy(
            booking, {"type": "refund", "refund_amount": 650.0}
        )
        self.assertTrue(ok)

    def test_compensation_six_hour_delay(self):
        booking = {"disruption_type": "delayed", "delay_hours": 6.0}
        ok, _ = evaluate_policy(
            booking, {"type": "compensation", "compensation_amount": 200.0}
        )
        self.assertTrue(ok)

    def test_compensation_cancelled_is_400(self):
        booking = {"disruption_type": "cancelled", "delay_hours": 0.0}
        ok, _ = evaluate_policy(
            booking, {"type": "compensation", "compensation_amount": 400.0}
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
