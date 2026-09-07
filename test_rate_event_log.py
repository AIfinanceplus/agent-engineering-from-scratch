import tempfile
import unittest
from pathlib import Path

from rate_event_log import EventLogError, RateEventLog


def envelope(message_type, run_id="run-1", **payload):
    return {"protocol": "rate-ndjson-v1", "type": message_type, "run_id": run_id, **payload}


class RateEventLogTests(unittest.TestCase):
    def test_append_is_durable_and_replay_preserves_order(self):
        with tempfile.TemporaryDirectory() as directory:
            log = RateEventLog(directory)
            log.append(envelope("start", execution_mode="parallel"))
            for sequence in (1, 2):
                log.append(envelope("event", event={"sequence": sequence, "run_id": "run-1"}))
            log.append(envelope("result", result={"run_id": "run-1", "eval": {"passed": True}}))
            restored = RateEventLog(Path(directory))
            messages = restored.read("run-1")
            self.assertEqual([message["type"] for message in messages], ["start", "event", "event", "result"])
            self.assertEqual(restored.snapshot("run-1"), {"run_id": "run-1", "message_count": 4, "event_count": 2, "terminal": True})

    def test_replay_cursor_and_order_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            log = RateEventLog(directory)
            log.append(envelope("start"))
            with self.assertRaises(EventLogError):
                log.append(envelope("event", event={"sequence": 2, "run_id": "run-1"}))
            log.append(envelope("event", event={"sequence": 1, "run_id": "run-1"}))
            log.append(envelope("event", event={"sequence": 2, "run_id": "run-1"}))
            self.assertEqual([item["event"]["sequence"] for item in log.read("run-1", after_sequence=1) if item["type"] == "event"], [2])
            with self.assertRaises(EventLogError):
                log.read("run-1", after_sequence=-1)


if __name__ == "__main__":
    unittest.main()
