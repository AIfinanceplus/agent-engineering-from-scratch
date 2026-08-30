import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import serve_r8
from serve_r9 import R9VisualizerHandler


def fake_eval_factory(blueprint, result, domain):
    return {
        "passed": 1,
        "total": 1,
        "pass_rate": 1.0,
        "cases": [{"case": {"case_id": "http-contract"}, "report": {"passed": True}}],
    }


class TestHandler(R9VisualizerHandler):
    eval_factory = staticmethod(fake_eval_factory)

    def log_message(self, format, *args):
        pass


class R9EvalHTTPTests(unittest.TestCase):
    def setUp(self):
        serve_r8.RUN_REGISTRY.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

        serve_r8.remember_run(
            {
                "ok": True,
                "run_id": "RUN-HTTP-TEST",
                "domain": "investment",
                "blueprint": {"queries": [{"query_id": "Q1"}]},
                "plan": {"status": "completed", "tasks": []},
                "evidence": [],
                "checkpoints": [],
            }
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        serve_r8.RUN_REGISTRY.clear()

    def post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, json.loads(raw)

    def test_repeated_eval_by_run_id_returns_json_without_research_rerun(self):
        for _ in range(2):
            status, headers, payload = self.post("/api/eval/current", {"run_id": "RUN-HTTP-TEST"})
            self.assertEqual(status, 200)
            self.assertEqual(payload["eval_transport"], "run_registry_v2")
            self.assertEqual(payload["evaluation_mode"], "existing_run_no_source_fetch")
            self.assertEqual(payload["eval_suite"]["passed"], 1)
            self.assertIn("application/json", headers.get("Content-Type", ""))
            self.assertEqual(headers.get("Connection"), "close")

    def test_missing_run_is_structured_json_not_connection_drop(self):
        status, _, payload = self.post("/api/eval/current", {"run_id": "RUN-MISSING"})
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "run_not_found")

    def test_invalid_request_is_structured_json(self):
        status, _, payload = self.post("/api/eval/current", {})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "run_id_required")

    def test_r9_page_is_no_store_and_loads_versioned_clients(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        cache_control = response.getheader("Cache-Control") or ""
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn("no-store", cache_control)
        self.assertIn("r8_eval_current.js?v=r9-eval-v2", body)
        self.assertIn("r9_ui.js?v=r9-eval-v2", body)


if __name__ == "__main__":
    unittest.main()
