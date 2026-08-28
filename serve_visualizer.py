"""Serve the V3 Agent Runtime visual debugger with Python's standard library.

Run:
    python serve_visualizer.py

Then open:
    http://127.0.0.1:8000
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import DEFAULT_MAX_RETRIES, DEFAULT_MAX_STEPS, run_agent
from model_adapters import FAKE_SCENARIOS, FakeModel
from tools import reset_teaching_tools


WEB_DIR = Path(__file__).parent / "web"


class VisualizerHandler(SimpleHTTPRequestHandler):
    """Serve static UI files and one endpoint that runs the real Runtime."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_POST(self):
        if self.path != "/api/run":
            self.send_error(404, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            request_data = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Request body must be valid JSON")
            return

        user_message = request_data.get("message", "Please calculate 10 + 20.")
        scenario = request_data.get("scenario", "success")
        max_steps = request_data.get("max_steps", DEFAULT_MAX_STEPS)
        max_retries = request_data.get("max_retries", DEFAULT_MAX_RETRIES)

        if scenario not in FAKE_SCENARIOS:
            self.send_json(
                400,
                {
                    "ok": False,
                    "error": f"Unknown scenario: {scenario}",
                    "events": [],
                },
            )
            return

        if (
            not isinstance(max_steps, int)
            or isinstance(max_steps, bool)
            or max_steps < 1
            or max_steps > 20
        ):
            self.send_json(
                400,
                {
                    "ok": False,
                    "error": "max_steps must be an integer from 1 to 20",
                    "events": [],
                },
            )
            return

        if (
            not isinstance(max_retries, int)
            or isinstance(max_retries, bool)
            or max_retries < 0
            or max_retries > 5
        ):
            self.send_json(
                400,
                {
                    "ok": False,
                    "error": "max_retries must be an integer from 0 to 5",
                    "events": [],
                },
            )
            return

        events = []
        reset_teaching_tools()

        try:
            final_answer = run_agent(
                user_message,
                model=FakeModel(scenario=scenario),
                on_event=events.append,
                max_steps=max_steps,
                max_retries=max_retries,
            )
            payload = {
                "ok": True,
                "scenario": scenario,
                "max_steps": max_steps,
                "max_retries": max_retries,
                "final_answer": final_answer,
                "events": events,
            }
            status = 200
        except Exception as exc:  # Debug UI should surface unexpected failures.
            payload = {
                "ok": False,
                "scenario": scenario,
                "max_steps": max_steps,
                "max_retries": max_retries,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500

        self.send_json(status, payload)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[visualizer] {format % args}")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Runtime Visual Debugger · V3")
    print("Open http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
