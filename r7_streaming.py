"""Small NDJSON protocol used by the UI V3 live Research Console.

The transport is intentionally one-way: a POST starts one research run and the
HTTP response yields newline-delimited JSON messages as Runtime/Scheduler events
happen. This keeps the current local server simple while making the UI genuinely
live instead of replaying a completed run.
"""

from __future__ import annotations

import json


STREAM_PROTOCOL = "r7-ndjson-v1"
STREAM_MESSAGE_TYPES = frozenset({"start", "event", "checkpoint", "result", "error"})


def stream_message(message_type: str, **payload) -> dict:
    if message_type not in STREAM_MESSAGE_TYPES:
        raise ValueError(f"Unsupported stream message type: {message_type}")
    return {
        "protocol": STREAM_PROTOCOL,
        "type": message_type,
        **payload,
    }


def encode_stream_message(message_type: str, **payload) -> bytes:
    message = stream_message(message_type, **payload)
    return (
        json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
