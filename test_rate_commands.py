import tempfile
import unittest

from rate_commands import RateIdempotencyStore


class RateCommandTests(unittest.TestCase):
    def test_same_key_applies_once_and_deduplicates_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RateIdempotencyStore(directory)
            command = {"action": "record_paper_fill", "quantity": 1}
            first = store.execute_once("PAPER-TRADE-001", command)
            second = store.execute_once("PAPER-TRADE-001", command)

            self.assertEqual(first["status"], "APPLIED")
            self.assertTrue(first["applied"])
            self.assertEqual(second["status"], "DEDUPLICATED")
            self.assertFalse(second["applied"])
            self.assertEqual(second["record"]["effect_count"], 1)

    def test_different_keys_are_independent_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RateIdempotencyStore(directory)
            first = store.execute_once("PAPER-TRADE-001", {"quantity": 1})
            second = store.execute_once("PAPER-TRADE-002", {"quantity": 1})
            self.assertTrue(first["applied"])
            self.assertTrue(second["applied"])


if __name__ == "__main__":
    unittest.main()
