import tempfile
import unittest

from rate_execution import ExecutionError, PaperExecutionTracker, partial_fill_cancel_race_demo, replay_execution


class PaperExecutionTests(unittest.TestCase):
    def test_cancel_race_accepts_late_fill_and_deduplicates_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = PaperExecutionTracker("ORDER-1", 100, path=f"{directory}/events.jsonl")
            tracker.accept(); tracker.record_fill("F1", 30); tracker.request_cancel()
            tracker.record_fill("F2", 20); tracker.record_fill("F2", 20); tracker.confirm_cancel()
            snapshot = tracker.snapshot()
            self.assertEqual(snapshot["state"], "CANCELED")
            self.assertEqual(snapshot["filled_quantity"], 50)
            self.assertEqual(snapshot["canceled_quantity"], 50)
            self.assertEqual(snapshot["remaining_quantity"], 0)
            self.assertEqual([e["event"] for e in tracker.events()], ["order_accepted", "fill_recorded", "cancel_requested", "fill_recorded", "fill_deduplicated", "cancel_confirmed"])
            self.assertEqual(replay_execution(f"{directory}/events.jsonl")["filled_quantity"], 50)

    def test_cancel_after_full_fill_is_noop(self):
        tracker = PaperExecutionTracker("ORDER-2", 10)
        tracker.accept(); tracker.record_fill("F1", 10)
        tracker.request_cancel()
        self.assertEqual(tracker.snapshot()["state"], "FILLED")
        self.assertEqual(tracker.events()[-1]["event"], "cancel_noop")

    def test_overfill_and_unaccepted_fill_are_rejected(self):
        tracker = PaperExecutionTracker("ORDER-3", 10)
        with self.assertRaisesRegex(ExecutionError, "accepted"):
            tracker.record_fill("F1", 1)
        tracker.accept()
        with self.assertRaisesRegex(ExecutionError, "exceeds"):
            tracker.record_fill("F1", 11)
        tracker.record_fill("F1", 5)
        with self.assertRaisesRegex(ExecutionError, "another quantity"):
            tracker.record_fill("F1", 6)

    def test_demo_contract(self):
        run = partial_fill_cancel_race_demo()
        self.assertEqual(run["execution"]["filled_quantity"], 50)
        self.assertEqual(run["execution"]["canceled_quantity"], 50)
        self.assertEqual(run["execution"]["guardrails"]["automatic_execution"], False)


if __name__ == "__main__":
    unittest.main()
