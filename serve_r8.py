"""R8 preview server on top of the accepted R7 runtime/streaming/checkpoint stack.

The transport and runtime remain R7-compatible. R8 replaces only the research
planner's D1 decision tool and the eval suite, which makes the stage easy to
compare against the accepted R7 baseline without rewriting orchestration.
"""

from http.server import ThreadingHTTPServer

import serve_visualizer as base
from r8_evals import make_r8_eval_suite
from r8_planner import R8ResearchPlanner
from r8_tooling import register_r8_tools


# The inherited handler resolves these names from the serve_visualizer module at
# runtime. Patch only this preview process; the source files and accepted R7 entry
# point remain unchanged.
base.R7ResearchPlanner = R8ResearchPlanner
base.make_r7_eval_suite = make_r8_eval_suite
register_r8_tools()


class R8VisualizerHandler(base.VisualizerHandler):
    def do_GET(self):
        if self.path not in {"/", "/index.html"}:
            return super().do_GET()

        source = (base.WEB_DIR / "index.html").read_text(encoding="utf-8")
        source = source.replace("Agent Research Workbench · R7 UI V3", "Agent Research Workbench · R8")
        source = source.replace('<span class="version">R7</span>', '<span class="version">R8</span>')
        source = source.replace('<strong>R7</strong><span class="status-sep">', '<strong>R8</strong><span class="status-sep">')
        source = source.replace(
            "</body>",
            '  <script src="r8_ui.js"></script>\n</body>',
        )
        body = source.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R8VisualizerHandler)
    print("Agent Research Workbench · R8 Professional Decision Lenses")
    print("Open http://127.0.0.1:8000")
    print("Shared runtime: R7 streaming / checkpoint / Evidence / Forecast contracts")
    print("R8 Investment: Market Pricing -> EV discipline -> Catalyst -> Position framework")
    print("R8 Policy: No-action baseline -> Options -> Counterfactual -> Distribution -> Implementation")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R8 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
