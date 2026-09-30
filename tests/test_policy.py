import unittest

from src.policy import evaluate_policy


class PolicyTests(unittest.TestCase):
    def test_rebook_rejects_upgrade(self):
        ok, reason = evaluate_policy(
            {"cabin_class": "economy", "departure_datetime": "2026-10-03T10:00:00"},
            {
                "type": "rebook",
                "flight": {
                    "cabin_class": "business",
                    "departure_datetime": "2026-10-03T16:00:00",
                    "connection_minutes": None,
                },
            },
        )
        self.assertFalse(ok)
        self.assertIn("Cabin upgrade", reason)

    def test_refund_full_on_cancel(self):
        ok, _ = evaluate_policy(
            {
                "fare_amount": 650.0,
                "tax_amount": 85.0,
                "disruption_type": "cancelled",
                "fare_type": "flex",
            },
            {"type": "refund", "refund_amount": 650.0},
        )
        self.assertTrue(ok)

    def test_compensation_6h(self):
        ok, _ = evaluate_policy(
            {"disruption_type": "delayed", "delay_hours": 6.0},
            {"type": "compensation", "compensation_amount": 200.0},
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
