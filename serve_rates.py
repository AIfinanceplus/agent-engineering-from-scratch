"""Serve the intentionally small Rate Strategy V1 workbench."""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from rate_agent import RateStrategyAgent


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
RATE_AGENT = RateStrategyAgent()


class RateStrategyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            self.path = "/rate_strategy.html"
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/rates/run-once":
            return self._send_json(404, {"ok": False, "error": {"code": "not_found", "message": "Not found"}})
        request_data = self._read_json()
        if request_data is None:
            return
        try:
            run = RATE_AGENT.run_once(
                lookback_days=request_data.get("lookback_days", 60),
                entry_z=request_data.get("entry_z", 1.0),
                holding_days=request_data.get("holding_days", 20),
                dv01_usd_per_bp=request_data.get("dv01_usd_per_bp", 100.0),
                round_trip_cost_bps=request_data.get("round_trip_cost_bps", 1.0),
                start_date=request_data.get("start_date"),
            )
        except Exception as exc:
            return self._send_json(
                400,
                {
                    "ok": False,
                    "action": "rate_strategy_run_once",
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
        return self._send_json(200, {"ok": True, "action": "rate_strategy_run_once", "run": run})

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(
                400,
                {"ok": False, "error": {"code": "invalid_json", "message": str(exc)}},
            )
            return None

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RateStrategyHandler)
    print("Rate Strategy V1 · one deterministic 2s10s paper simulation")
    print(f"Open http://{host}:{port}")
    print("D1 public FRED data -> S1 explicit rule -> one closed paper trade -> E1 eval")
    print("No event search, no market matching, no broker connection, no automatic execution")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
