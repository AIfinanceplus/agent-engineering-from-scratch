"""R8 preview server on top of the accepted R7 runtime/streaming/checkpoint stack.

This module is also the transport base for R9. Research execution stays in the
accepted R7 runtime, while the preview swaps Planner/Eval contracts.

Eval reliability rule:
- research results are retained in a small in-memory Run Registry;
- the browser evaluates by run_id instead of POSTing the whole run back;
- every application-level Eval failure returns structured JSON;
- HTML/JS are served no-store so stale Eval clients do not survive a restart.
"""

from collections import OrderedDict
from http.server import ThreadingHTTPServer
import json

import serve_visualizer as base
from r8_eval_current import evaluate_current_run
from r8_evals import make_r8_eval_suite
from r8_planner import R8ResearchPlanner
from r8_tooling import register_r8_tools


base.R7ResearchPlanner = R8ResearchPlanner
base.make_r7_eval_suite = make_r8_eval_suite
register_r8_tools()

MAX_REGISTERED_RUNS = 16
RUN_REGISTRY: OrderedDict[str, dict] = OrderedDict()
EVAL_PATHS = {"/api/eval/current", "/api/r8/eval"}


def remember_run(result: dict) -> None:
    if not isinstance(result, dict):
        return
    run_id = result.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return
    RUN_REGISTRY[run_id] = result
    RUN_REGISTRY.move_to_end(run_id)
    while len(RUN_REGISTRY) > MAX_REGISTERED_RUNS:
        RUN_REGISTRY.popitem(last=False)


class R8VisualizerHandler(base.VisualizerHandler):
    version_label = "R8"
    page_title = "Agent Research Workbench · R8"
    extra_scripts = ("r8_ui.js", "r8_eval_current.js")
    eval_factory = staticmethod(make_r8_eval_suite)

    def end_headers(self):
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"} or path.endswith((".js", ".html")):
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
            return super().do_GET()

        source = (base.WEB_DIR / "index.html").read_text(encoding="utf-8")
        source = source.replace("Agent Research Workbench · R7 UI V3", self.page_title)
        source = source.replace('<span class="version">R7</span>', f'<span class="version">{self.version_label}</span>')
        source = source.replace('<strong>R7</strong><span class="status-sep">', f'<strong>{self.version_label}</strong><span class="status-sep">')
        scripts = "\n".join(
            f'  <script src="{name}?v={self.version_label.lower()}-eval-v2"></script>'
            for name in self.extra_scripts
        )
        source = source.replace("</body>", f"{scripts}\n</body>")
        body = source.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def execute_research(self, *args, **kwargs) -> dict:
        result = super().execute_research(*args, **kwargs)
        remember_run(result)
        return result

    def do_POST(self):
        if self.path not in EVAL_PATHS:
            return super().do_POST()

        request_data = self._read_eval_request()
        if request_data is None:
            return

        run_id = request_data.get("run_id")
        research_result = None
        if isinstance(run_id, str) and run_id:
            research_result = RUN_REGISTRY.get(run_id)
            if research_result is None:
                self._send_eval_json(
                    404,
                    {
                        "ok": False,
                        "action": "eval_current_run",
                        "error": {
                            "code": "run_not_found",
                            "message": f"Run {run_id} is not available in this server process. Run Research again, then Eval.",
                        },
                    },
                )
                return
        elif isinstance(request_data.get("research_result"), dict):
            # Compatibility path for a stale pre-v2 browser tab. It returns JSON
            # rather than dropping the connection, but the active UI never needs it.
            research_result = request_data["research_result"]
            remember_run(research_result)
        else:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "eval_current_run",
                    "error": {
                        "code": "run_id_required",
                        "message": "Eval requires run_id from a completed Research run.",
                    },
                },
            )
            return

        try:
            payload = evaluate_current_run(research_result, eval_factory=type(self).eval_factory)
            payload["action"] = "eval_current_run"
            payload["eval_transport"] = "run_registry_v2"
        except Exception as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "eval_current_run",
                    "run_id": research_result.get("run_id") if isinstance(research_result, dict) else None,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return
        self._send_eval_json(200, payload)

    def _read_eval_request(self) -> dict | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 0 or content_length > 12_000_000:
                raise ValueError("invalid Content-Length")
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            return payload
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "eval_current_run",
                    "error": {"code": "invalid_eval_request", "message": str(exc)},
                },
            )
            return None

    def _send_eval_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R8VisualizerHandler)
    print("Agent Research Workbench · R8 Professional Decision Lenses")
    print("Open http://127.0.0.1:8000")
    print("Shared runtime: R7 streaming / checkpoint / Evidence / Forecast contracts")
    print("R8 Investment: Market Pricing -> EV discipline -> Catalyst -> Position framework")
    print("R8 Policy: No-action baseline -> Options -> Counterfactual -> Distribution -> Implementation")
    print("Evals: POST /api/eval/current with run_id -> Run Registry -> checks; NO source re-fetch")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R8 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
