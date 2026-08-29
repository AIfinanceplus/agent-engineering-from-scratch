from pathlib import Path
import unittest


ROOT = Path(__file__).parent
WEB = ROOT / "web"


class UIV3StreamContractTests(unittest.TestCase):
    def test_active_page_loads_fixed_grid_and_live_stream_assets(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('r7_v3.css', html)
        self.assertIn('r7_v3_stream.css', html)
        self.assertIn('r7_v3.js', html)
        self.assertIn('r7_v3_stream.js', html)
        self.assertIn('data-nav="checkpoints"', html)
        self.assertIn('data-detail-tab="checkpoint"', html)
        self.assertIn('data-inspector-tab="checkpoint"', html)

    def test_layout_contract_prevents_sidebar_and_inspector_overlap(self):
        css = (WEB / "r7_v3.css").read_text(encoding="utf-8")
        compact = "".join(css.split())
        self.assertIn('display:grid;grid-template-columns:var(--sidebar)minmax(0,1fr)var(--inspector)', compact)
        self.assertIn('pointer-events:auto', css)
        self.assertIn('.inspector{grid-column:3', compact)
        self.assertIn('.workspace{grid-column:2', compact)

    def test_live_client_consumes_real_ndjson_stream(self):
        js = (WEB / "r7_v3_stream.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/stream'", js)
        self.assertIn('response.body.getReader()', js)
        self.assertIn("message.protocol !== 'r7-ndjson-v1'", js)
        self.assertIn('applyLiveEvent', js)
        self.assertIn('applyLiveCheckpoint', js)
        self.assertIn('runResearch = streamRunResearch', js)


if __name__ == "__main__":
    unittest.main()
