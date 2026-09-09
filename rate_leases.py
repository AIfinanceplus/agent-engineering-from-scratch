"""Small deterministic lease/fencing coordinator for the agent-engineering lesson.

This is intentionally an in-memory teaching implementation.  The important
contract is that every takeover increments a fencing token and every owner
must present the current token immediately before a side effect.
"""

import time
from copy import deepcopy


class LeaseError(RuntimeError):
    pass


class LeaseHeld(LeaseError):
    pass


class LeaseFenced(LeaseError):
    pass


class LeaseCoordinator:
    def __init__(self, *, clock=None):
        self.clock = clock or time.monotonic
        self._leases = {}

    def acquire(self, resource, owner, *, ttl_ms=1000):
        if not resource or not owner or ttl_ms <= 0:
            raise ValueError("resource, owner and positive ttl_ms are required")
        now = self.clock()
        current = self._leases.get(resource)
        if current and current["expires_at"] > now and current["owner"] != owner:
            raise LeaseHeld(f"lease for {resource} is held by {current['owner']}")
        token = (current["fencing_token"] if current else 0) + 1
        row = {"resource": resource, "owner": owner, "fencing_token": token,
               "ttl_ms": ttl_ms, "acquired_at": now,
               "expires_at": now + ttl_ms / 1000}
        self._leases[resource] = row
        return deepcopy(row)

    def renew(self, resource, owner, fencing_token, *, ttl_ms=None):
        current = self._require_current(resource, owner, fencing_token)
        now = self.clock()
        if current["expires_at"] <= now:
            raise LeaseFenced("lease expired before renewal")
        duration = ttl_ms if ttl_ms is not None else current["ttl_ms"]
        if duration <= 0:
            raise ValueError("positive ttl_ms is required")
        current["ttl_ms"] = duration
        current["expires_at"] = now + duration / 1000
        return deepcopy(current)

    def fence_check(self, resource, owner, fencing_token):
        current = self._require_current(resource, owner, fencing_token)
        if current["expires_at"] <= self.clock():
            raise LeaseFenced("lease expired; owner is fenced")
        return deepcopy(current)

    def expire(self, resource):
        current = self._leases.get(resource)
        if current:
            current["expires_at"] = self.clock() - 0.001

    def release(self, resource, owner, fencing_token):
        current = self._require_current(resource, owner, fencing_token)
        del self._leases[resource]
        return deepcopy(current)

    def snapshot(self, resource):
        return deepcopy(self._leases.get(resource))

    def _require_current(self, resource, owner, fencing_token):
        current = self._leases.get(resource)
        if current is None:
            raise LeaseFenced("lease does not exist")
        if current["owner"] != owner or current["fencing_token"] != fencing_token:
            raise LeaseFenced("stale owner or fencing token")
        return current
