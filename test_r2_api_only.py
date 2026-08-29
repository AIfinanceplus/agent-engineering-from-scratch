import unittest
from urllib.error import URLError
from urllib.parse import unquote

from api_sources import BLSPublicAPI, EIAPublicAPI, FREDPublicAPI, _urlopen_json
from r2_api_evals import APIEvalCase, score_api_result
from r2_api_planner import APIMacroPlanner


BLS_ROWS = [
    {"year": "2025", "period": "M06", "periodName": "June", "value": "100.0", "footnotes": []},
    {"year": "2026", "period": "M06", "periodName": "June", "value": "103.0", "footnotes": []},
]


def bls_payload(series_id="CUSR0000SA0"):
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"seriesID": series_id, "data": BLS_ROWS}]},
    }


class APIOnlySourceTests(unittest.TestCase):
    def test_bls_uses_v2_api_and_normalizes_history(self):
        captured = []

        def transport(url):
            captured.append(url)
            return bls_payload()

        result = BLSPublicAPI(transport=transport).fetch("CUSR0000SA0", "Headline CPI")
        self.assertEqual(result["source_mode"], "api")
        self.assertEqual(result["provider"], "BLS")
        self.assertEqual(result["as_of"], "2026-06")
        self.assertTrue(captured[0].startswith("https://api.bls.gov/publicAPI/v2/timeseries/data/"))
        self.assertTrue(captured[0].endswith("/CUSR0000SA0"))
        self.assertEqual(result["transport"], "GET")
        self.assertNotIn("fixture", str(result).lower())

    def test_bls_default_path_falls_back_from_get_to_post(self):
        calls = []

        def get_transport(url):
            calls.append(("GET", url))
            raise ConnectionError("simulated GET connection reset")

        def post_transport(url, payload):
            calls.append(("POST", url, payload))
            return bls_payload()

        api = BLSPublicAPI()
        api._transport = get_transport
        api._post_transport = post_transport
        api._custom_transport = False
        result = api.fetch("CUSR0000SA0", "Headline CPI")

        self.assertEqual(result["transport"], "POST")
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1][0], "POST")
        self.assertTrue(calls[1][1].endswith("/v2/timeseries/data/"))
        self.assertEqual(calls[1][2], {"seriesid": ["CUSR0000SA0"]})

    def test_bls_reports_both_transport_failures(self):
        api = BLSPublicAPI()
        api._transport = lambda url: (_ for _ in ()).throw(ConnectionError("GET reset"))
        api._post_transport = lambda url, payload: (_ for _ in ()).throw(ConnectionError("POST reset"))
        api._custom_transport = False

        with self.assertRaises(ConnectionError) as caught:
            api.fetch("CUSR0000SA0", "Headline CPI")
        message = str(caught.exception)
        self.assertIn("GET=ConnectionError: GET reset", message)
        self.assertIn("POST=ConnectionError: POST reset", message)

    def test_fred_requests_recent_json_window_without_leaking_key_to_evidence(self):
        captured = []

        def transport(url):
            captured.append(url)
            return {"observations": [
                {"date": "2026-08-01", "value": "2.30"},
                {"date": "2026-08-08", "value": "2.35"},
            ]}

        result = FREDPublicAPI(transport=transport, env={"FRED_API_KEY": "secretfred"}).fetch("T5YIE", "5Y Breakeven", "percent")
        decoded = unquote(captured[0])
        self.assertIn("file_type=json", decoded)
        self.assertIn("sort_order=desc", decoded)
        self.assertIn("limit=8", decoded)
        self.assertIn("api_key=secretfred", decoded)
        self.assertNotIn("secretfred", str(result))
        self.assertEqual(result["provider"], "FRED")

    def test_eia_uses_current_petroleum_rest_route(self):
        captured = []

        def transport(url):
            captured.append(url)
            return {"response": {"data": [
                {"period": "2026-08-04", "value": "3.20"},
                {"period": "2026-08-11", "value": "3.25"},
            ]}}

        result = EIAPublicAPI(transport=transport, env={"EIA_API_KEY": "secreteia"}).fetch(
            "EMM_EPMR_PTE_NUS_DPG", "Regular Gasoline", "dollars_per_gallon"
        )
        decoded = unquote(captured[0])
        self.assertTrue(captured[0].startswith("https://api.eia.gov/v2/petroleum/pri/gnd/data/?"))
        self.assertIn("frequency=weekly", decoded)
        self.assertIn("facets[series][]=EMM_EPMR_PTE_NUS_DPG", decoded)
        self.assertIn("data[0]=value", decoded)
        self.assertIn("length=8", decoded)
        self.assertNotIn("secreteia", str(result))
        self.assertEqual(result["provider"], "EIA")


class APIOnlyPlannerEvalTests(unittest.TestCase):
    def test_planner_has_no_fixture_or_mode_argument(self):
        plan = APIMacroPlanner().plan("test", reference_date="2026-08-29")
        self.assertEqual([task.task_id for task in plan.tasks], ["H1", "C1", "F1", "G1", "A1"])
        self.assertEqual(plan.tasks[-1].depends_on, ["H1", "C1", "F1", "G1"])
        for task in plan.tasks:
            self.assertNotIn("mode", task.arguments)
            self.assertNotIn("fixture", str(task.arguments).lower())

    def test_api_eval_uses_h1_c1_f1_g1_a1(self):
        tasks = [
            {"task_id": task_id, "status": "completed"}
            for task_id in ("H1", "C1", "F1", "G1", "A1")
        ]
        evidence = [
            {"evidence_id": "BLS:H", "provider": "BLS"},
            {"evidence_id": "BLS:C", "provider": "BLS"},
            {"evidence_id": "FRED:F", "provider": "FRED"},
            {"evidence_id": "EIA:G", "provider": "EIA"},
        ]
        citations = [
            {"evidence_id": item["evidence_id"], "citation": f"[{item['evidence_id']}]"}
            for item in evidence
        ]
        result = {
            "ok": True,
            "plan": {"status": "completed", "tasks": tasks},
            "evidence": evidence,
            "citations": citations,
            "final_artifact": {
                "answer": "Descriptive signals; not causal attribution.",
                "freshness": {item["evidence_id"]: {"status": "fresh"} for item in evidence},
                "limitations": ["not causal"],
            },
            "trace": {"metrics": {"tool_attempts": 5}},
        }
        report = score_api_result(APIEvalCase("api-contract"), result)
        self.assertTrue(report["passed"], report["failures"])
        serialized = str(report)
        self.assertIn("H1", str(APIEvalCase("api-contract").expected_tasks))
        self.assertNotIn("E1", serialized)
        self.assertNotIn("E2", serialized)


if __name__ == "__main__":
    unittest.main()
