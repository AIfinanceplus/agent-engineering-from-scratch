"""Serve the V0.2 Agent Runtime visual debugger with Python's standard library.

Run:
    python serve_visualizer.py

Then open:
    http://127.0.0.1:8000
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import run_agent
from model_adapters import FakeModel


WEB_DIR = Path(__file__).parent / "web"


class VisualizerHandler(SimpleHTTPRequestHandler):
    """Serve static UI files and one tiny endpoint that runs the real runtime."""

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
        events = []

        try:
            final_answer = run_agent(
                user_message,
                model=FakeModel(),
                on_event=events.append,
            )
            payload = {
                "ok": True,
                "final_answer": final_answer,
                "events": events,
            }
            status = 200
        except Exception as exc:  # Debug UI should show runtime failures as data.
            payload = {
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Keep terminal output readable while learning.
        print(f"[visualizer] {format % args}")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Runtime Visual Debugger")
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
