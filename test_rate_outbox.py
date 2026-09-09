import tempfile
import unittest

from rate_outbox import IdempotentEffectSink, OutboxCrash, OutboxFenced, OutboxStore


class RateOutboxTests(unittest.TestCase):
    def test_retry_same_key_deduplicates_sink_after_ack_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OutboxStore(directory)
            sink = IdempotentEffectSink(f"{directory}/effects")
            command = {"action": "record_paper_fill", "paper_trade_id": "PAPER-1"}
            store.enqueue("run-1-fill-1", command, fencing_token=2)
            with self.assertRaises(OutboxCrash):
                store.dispatch("run-1-fill-1", owner="runtime-B", fencing_token=2,
                                sink=sink, crash_after_apply=True)
            retry = store.dispatch("run-1-fill-1", owner="runtime-B", fencing_token=2, sink=sink)
            self.assertEqual(retry["status"], "DEDUPLICATED")
            self.assertFalse(retry["applied"])
            self.assertEqual(retry["sink"]["effect_count"], 1)
            self.assertEqual(store.snapshot("run-1-fill-1")["attempts"], 2)
            self.assertEqual(store.snapshot("run-1-fill-1")["status"], "ACKNOWLEDGED")

    def test_same_key_cannot_change_command(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OutboxStore(directory)
            store.enqueue("run-1-fill-1", {"action": "a"}, fencing_token=1)
            with self.assertRaisesRegex(ValueError, "already bound"):
                store.enqueue("run-1-fill-1", {"action": "b"}, fencing_token=1)

    def test_fencing_rejects_before_sink_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OutboxStore(directory)
            sink = IdempotentEffectSink(f"{directory}/effects")
            store.enqueue("run-1-fill-1", {"action": "record"}, fencing_token=2)
            with self.assertRaises(OutboxFenced):
                store.dispatch("run-1-fill-1", owner="runtime-A", fencing_token=1, sink=sink,
                                fence_check=lambda owner, token: (_ for _ in ()).throw(
                                    OutboxFenced("stale token")))
            self.assertEqual(list((sink.directory).glob("*.json")), [])
            self.assertEqual(store.snapshot("run-1-fill-1")["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
