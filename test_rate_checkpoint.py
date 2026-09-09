import tempfile
import unittest

from rate_agent import RateSimulatedCrash, RateStrategyAgent
from rate_checkpoint import RateCheckpointStore
from test_rate_strategy import completed_steepener_history


class RateCheckpointTests(unittest.TestCase):
    def test_crash_after_d1_then_resume_skips_d1(self):
        calls = []

        def fetch(**kwargs):
            calls.append(kwargs)
            return completed_steepener_history()

        with tempfile.TemporaryDirectory() as directory:
            store = RateCheckpointStore(directory)
            agent = RateStrategyAgent({"fetch_public_rate_history": fetch})
            with self.assertRaises(RateSimulatedCrash) as raised:
                agent.run_once(
                    start_date="2026-01-01",
                    checkpoint_store=store,
                    crash_after_task="D1",
                )

            crash = raised.exception
            self.assertEqual(crash.task_id, "D1")
            self.assertTrue(store.exists(crash.run_id))
            checkpoint = store.load(crash.run_id)
            self.assertEqual(checkpoint["boundary"], "after_D1")
            self.assertEqual(checkpoint["next_task"], "S1")
            self.assertEqual(checkpoint["completed_task_ids"], ["D1"])
            self.assertEqual(len(calls), 1)

            resumed = agent.run_once(
                start_date="2026-01-01",
                checkpoint_store=store,
                resume=True,
            )

            self.assertTrue(resumed["eval"]["passed"])
            self.assertTrue(resumed["recovery"]["resumed"])
            self.assertTrue(resumed["recovery"]["durable"])
            self.assertEqual(len(calls), 1, "resume must not call D1 again")
            events = [row["event"] for row in resumed["trace"]]
            self.assertIn("checkpoint_loaded", events)
            self.assertIn("resume_boundary", events)
            self.assertIn("task_skipped_from_checkpoint", events)
            self.assertEqual(events[-1], "checkpoint_saved")
            self.assertEqual(len(resumed["checkpoints"]), 4)
            self.assertEqual(
                [row["boundary"] for row in resumed["checkpoints"]],
                ["after_plan_created", "after_D1", "after_S1", "after_E1"],
            )

    def test_resume_requires_matching_checkpoint_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RateCheckpointStore(directory)
            agent = RateStrategyAgent(
                {"fetch_public_rate_history": lambda **_kwargs: completed_steepener_history()}
            )
            with self.assertRaises(RateSimulatedCrash) as raised:
                agent.run_once(
                    start_date="2026-01-01",
                    checkpoint_store=store,
                    crash_after_task="D1",
                )
            with self.assertRaisesRegex(RuntimeError, "configuration"):
                agent.run_once(
                    start_date="2026-01-01",
                    holding_days=10,
                    run_id=raised.exception.run_id,
                    checkpoint_store=store,
                    resume=True,
                )

    def test_resume_without_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "no checkpoint"):
                RateStrategyAgent().run_once(
                    start_date="2026-01-01",
                    run_id="RATE-RUN-MISSING",
                    checkpoint_store=RateCheckpointStore(directory),
                    resume=True,
                )


if __name__ == "__main__":
    unittest.main()
