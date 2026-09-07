import unittest

from rate_leases import LeaseCoordinator, LeaseFenced, LeaseHeld


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class LeaseCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.leases = LeaseCoordinator(clock=self.clock)

    def test_active_lease_is_exclusive(self):
        first = self.leases.acquire("rate-run", "runtime-A", ttl_ms=1000)
        self.assertEqual(first["fencing_token"], 1)
        with self.assertRaises(LeaseHeld):
            self.leases.acquire("rate-run", "runtime-B", ttl_ms=1000)

    def test_expired_takeover_increments_fencing_token(self):
        first = self.leases.acquire("rate-run", "runtime-A", ttl_ms=1000)
        self.clock.advance(1.1)
        second = self.leases.acquire("rate-run", "runtime-B", ttl_ms=1000)
        self.assertEqual(second["fencing_token"], 2)
        with self.assertRaises(LeaseFenced):
            self.leases.fence_check("rate-run", "runtime-A", first["fencing_token"])
        self.assertEqual(self.leases.fence_check("rate-run", "runtime-B", 2)["owner"], "runtime-B")

    def test_renew_keeps_owner_and_token(self):
        first = self.leases.acquire("rate-run", "runtime-A", ttl_ms=1000)
        self.clock.advance(0.5)
        renewed = self.leases.renew("rate-run", "runtime-A", first["fencing_token"], ttl_ms=2000)
        self.assertEqual(renewed["fencing_token"], first["fencing_token"])
        self.assertEqual(renewed["owner"], "runtime-A")

    def test_expired_owner_cannot_renew_or_release(self):
        first = self.leases.acquire("rate-run", "runtime-A", ttl_ms=1000)
        self.clock.advance(1.1)
        with self.assertRaises(LeaseFenced):
            self.leases.renew("rate-run", "runtime-A", first["fencing_token"])


if __name__ == "__main__":
    unittest.main()
