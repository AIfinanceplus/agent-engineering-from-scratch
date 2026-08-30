"""R9 preview server: R8 professional decisions + separate Market Context lane."""

from http.server import ThreadingHTTPServer

import serve_visualizer as runtime
import serve_r8 as r8
from r9_evals import make_r9_eval_suite
from r9_planner import R9ResearchPlanner
from r9_tooling import register_r9_tools


runtime.R7ResearchPlanner = R9ResearchPlanner
runtime.make_r7_eval_suite = make_r9_eval_suite
register_r9_tools()


class R9VisualizerHandler(r8.R8VisualizerHandler):
    version_label = "R9"
    page_title = "Agent Research Workbench · R9 Market Pricing Context"
    extra_scripts = ("r8_ui.js", "r8_eval_current.js", "r9_ui.js")
    eval_factory = staticmethod(make_r9_eval_suite)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R9VisualizerHandler)
    print("Agent Research Workbench · R9 Market Pricing Context")
    print("Open http://127.0.0.1:8000")
    print("Research lane: Question -> Research Evidence -> S1 -> D1 -> F1")
    print("Investment context lane: FRED market Evidence -> M6 MarketPricingSnapshot")
    print("R9 does NOT infer Fed path, mispricing, EV, or position; those remain R10 work.")
    print("Eval: /api/eval/current -> Run Registry -> R9 six-contract suite; no source re-fetch")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R9 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
