import json
import unittest

from r7_streaming import STREAM_PROTOCOL, encode_stream_message, stream_message


class R7StreamingProtocolTests(unittest.TestCase):
    def test_stream_message_has_versioned_protocol_and_type(self):
        message = stream_message("event", event={"type": "task_started", "task_id": "Q1"})
        self.assertEqual(message["protocol"], STREAM_PROTOCOL)
        self.assertEqual(message["type"], "event")
        self.assertEqual(message["event"]["task_id"], "Q1")

    def test_ndjson_encoder_writes_exactly_one_line(self):
        encoded = encode_stream_message("checkpoint", checkpoint={"checkpoint_id": "CP-002"})
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(encoded.count(b"\n"), 1)
        decoded = json.loads(encoded.decode("utf-8"))
        self.assertEqual(decoded["type"], "checkpoint")
        self.assertEqual(decoded["checkpoint"]["checkpoint_id"], "CP-002")

    def test_unknown_message_type_fails_closed(self):
        with self.assertRaises(ValueError):
            stream_message("progress_guess", value=50)


if __name__ == "__main__":
    unittest.main()
