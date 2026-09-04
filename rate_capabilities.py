"""Signed, least-privilege capability tickets for the teaching Runtime."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from uuid import uuid4


TOOL_SCOPES = {
    "fetch_public_rate_history": "rates:read",
    "prepare_rate_series": "rates:transform",
    "join_rate_series": "rates:join",
    "simulate_one_curve_trade": "paper:simulate",
}


class CapabilityRejected(PermissionError):
    def __init__(self, message, reasons):
        self.reasons = list(reasons)
        super().__init__(message)


@dataclass(frozen=True)
class CapabilityTicket:
    cap_id: str
    run_id: str
    task_id: str
    tool_name: str
    scope: str
    issued_at: str
    expires_at: str
    max_uses: int
    signature: str

    def claims(self):
        return {key: value for key, value in self.__dict__.items() if key != "signature"}

    def public_record(self):
        return {**self.claims(), "signature": f"{self.signature[:12]}…"}


class CapabilityAuthority:
    def __init__(self, secret=None):
        self._secret = secret or secrets.token_bytes(32)
        self._uses = {}

    def _sign(self, claims):
        payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def mint(self, *, run_id, task_id, tool_name, scope, ttl_seconds=60, now=None):
        now = now or datetime.now(timezone.utc)
        claims = {
            "cap_id": f"CAP-{uuid4().hex[:12]}", "run_id": run_id,
            "task_id": task_id, "tool_name": tool_name, "scope": scope,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "max_uses": 1,
        }
        return CapabilityTicket(**claims, signature=self._sign(claims))

    def authorize(self, ticket, *, run_id, task_id, tool_name, required_scope, now=None):
        now = now or datetime.now(timezone.utc)
        reasons = []
        if not hmac.compare_digest(ticket.signature, self._sign(ticket.claims())):
            reasons.append("signature_invalid")
        if ticket.run_id != run_id:
            reasons.append("run_id_mismatch")
        if ticket.task_id != task_id:
            reasons.append("task_id_mismatch")
        if ticket.tool_name != tool_name:
            reasons.append("tool_not_authorized")
        if ticket.scope != required_scope:
            reasons.append("scope_not_authorized")
        if now >= datetime.fromisoformat(ticket.expires_at):
            reasons.append("capability_expired")
        if self._uses.get(ticket.cap_id, 0) >= ticket.max_uses:
            reasons.append("capability_already_consumed")
        if reasons:
            raise CapabilityRejected("capability rejected: " + ", ".join(reasons), reasons)
        self._uses[ticket.cap_id] = self._uses.get(ticket.cap_id, 0) + 1
        return {"authorized": True, "cap_id": ticket.cap_id,
                "consumed_uses": self._uses[ticket.cap_id], "max_uses": ticket.max_uses}

    def snapshot(self):
        return {"signing": "HMAC-SHA256", "default_max_uses": 1,
                "used_capabilities": dict(self._uses), "secret_exposed": False}
