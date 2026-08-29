import unittest
from datetime import date
from unittest.mock import patch

import api_sources_native
from api_sources import SourceAPIError
from r4_source_health import SourceHealthChecker
from source_smoke import build_parser, normalize_providers


def evidence(provider, series_id, as_of):
    return {
        "kind": "evidence",
        "evidence_id": f"{provider}:{series_id}",
        "claim": "test",
        "value": 1.0,
        "unit": "test_unit",
        "confidence": 1.0,
        "as_of": as_of,
        "history": [{"period": as_of, "value": 1.0}],
        "source": {
            "source_id": f"{provider}:{series_id}",
            "title": "test",
            "publisher": provider,
            "uri": "https://example.invalid/source",
        },
        "transport": "GET" if provider == "BLS" else None,
    }


def bls_payload(series_id="CUSR0000SA0"):
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [{
                "seriesID": series_id,
                "data": [
                    {"year": "2026", "period": "M07", "periodName": "July", "value": "323.1", "footnotes": []}
                ],
            }]
        },
    }


class SourceSmokeCLITests(unittest.TestCase):
    def test_no_provider_arguments_mean_all_sources(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.providers, [])
        self.assertIsNone(normalize_providers(args.providers))

    def test_provider_arguments_are_case_insensitive(self):
        self.assertEqual(normalize_providers(["bls", "fred"]), ["BLS", "FRED"])

    def test_invalid_provider_is_rejected_by_manual_validation(self):
        with self.assertRaises(ValueError):
            normalize_providers(["NOAA"])


class SourceHealthTests(unittest.TestCase):
    def test_missing_credentials_are_reported_without_calling_protected_sources(self):
        calls = []

        def bls(series_id, label):
            calls.append("BLS")
            return evidence("BLS", series_id, "2026-08")

        def should_not_run(*args):
            calls.append("PROTECTED")
            raise AssertionError("credential-gated fetcher should not run")

        checker = SourceHealthChecker(
            fetchers={"BLS": bls, "FRED": should_not_run, "EIA": should_not_run},
            env={},
            today=date(2026, 8, 29),
        )
        report = checker.run()
        self.assertEqual(report["overall"], "PARTIAL")
        self.assertEqual(calls, ["BLS"])
        statuses = {item["provider"]: item["status"] for item in report["results"]}
        self.assertEqual(statuses["BLS"], "READY")
        self.assertEqual(statuses["FRED"], "CREDENTIAL_MISSING")
        self.assertEqual(statuses["EIA"], "CREDENTIAL_MISSING")

    def test_all_sources_ready_with_valid_evidence_contract(self):
        fetchers = {
            "BLS": lambda series_id, label: evidence("BLS", series_id, "2026-08"),
            "FRED": lambda series_id, label, unit: evidence("FRED", series_id, "2026-08-28"),
            "EIA": lambda series_id, label, unit: evidence("EIA", series_id, "2026-08-24"),
        }
        checker = SourceHealthChecker(
            fetchers=fetchers,
            env={"FRED_API_KEY": "fred-secret", "EIA_API_KEY": "eia-secret"},
            today=date(2026, 8, 29),
        )
        report = checker.run()
        self.assertTrue(report["ready"])
        self.assertEqual(report["overall"], "READY")
        self.assertEqual(report["ready_count"], 3)
        serialized = str(report)
        self.assertNotIn("fred-secret", serialized)
        self.assertNotIn("eia-secret", serialized)
        bls = report["results"][0]
        self.assertEqual(bls["optional_credential_names"], ["BLS_API_KEY"])
        self.assertFalse(bls["optional_credentials_present"])
        for item in report["results"]:
            self.assertEqual(item["status"], "READY")
            self.assertTrue(item["endpoint"].startswith("https://"))
            self.assertNotIn("api_key", item["endpoint"].lower())
            self.assertIn(item["freshness"], {"FRESH", "AGING", "STALE", "UNKNOWN"})

    def test_bls_daily_threshold_is_rate_limited_with_registered_key_hint(self):
        def quota_exhausted(series_id, label):
            raise SourceAPIError(
                "BLS",
                "request failed: ['Request could not be serviced, as the daily threshold for total number of requests allocated to the user with registration key has been reached.']",
            )

        checker = SourceHealthChecker(fetchers={"BLS": quota_exhausted}, env={}, today=date(2026, 8, 29))
        result = checker.check("BLS").to_dict()
        self.assertEqual(result["status"], "RATE_LIMITED")
        self.assertFalse(result["ready"])
        self.assertIn("BLS_API_KEY", result["recovery_hint"])
        self.assertEqual(result["optional_credential_names"], ["BLS_API_KEY"])
        self.assertFalse(result["optional_credentials_present"])

    def test_registered_bls_uses_post_payload_and_never_leaks_key(self):
        secret = "registered-bls-secret"
        captured = []

        def fake_post(url, payload):
            captured.append((url, dict(payload)))
            return bls_payload()

        with patch.dict("os.environ", {"BLS_API_KEY": secret}, clear=False), patch.object(
            api_sources_native, "http_post_json", side_effect=fake_post
        ):
            result = api_sources_native.fetch_bls_api_series("CUSR0000SA0", "Headline CPI")

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][1]["registrationkey"], secret)
        self.assertEqual(result["transport"], "POST_REGISTERED")
        self.assertNotIn(secret, str(result))
        self.assertNotIn("registrationkey", str(result).lower())

    def test_contract_error_is_distinct_from_transport_error(self):
        def bad_bls(series_id, label):
            payload = evidence("BLS", series_id, "2026-08")
            payload.pop("history")
            return payload

        checker = SourceHealthChecker(
            fetchers={"BLS": bad_bls},
            env={},
            today=date(2026, 8, 29),
        )
        result = checker.check("BLS").to_dict()
        self.assertEqual(result["status"], "CONTRACT_ERROR")
        self.assertFalse(result["ready"])
        self.assertIn("missing history", result["error_message"])

    def test_tls_failure_is_classified_without_disabling_verification(self):
        def tls_failure(series_id, label):
            raise ConnectionError(
                "SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
            )

        checker = SourceHealthChecker(
            fetchers={"BLS": tls_failure},
            env={},
            today=date(2026, 8, 29),
        )
        result = checker.check("BLS").to_dict()
        self.assertEqual(result["status"], "TLS_ERROR")
        self.assertFalse(result["ready"])

    def test_runtime_secret_is_redacted_from_exception_diagnostics(self):
        secret = "super-secret-fred-key"

        def leaking_fetcher(series_id, label, unit):
            raise RuntimeError(f"upstream rejected key {secret}")

        with patch.dict("os.environ", {"FRED_API_KEY": secret}, clear=False):
            checker = SourceHealthChecker(
                fetchers={"FRED": leaking_fetcher},
                env={"FRED_API_KEY": secret},
                today=date(2026, 8, 29),
            )
            result = checker.check("FRED").to_dict()
        self.assertNotIn(secret, str(result))
        self.assertIn("redacted", result["error_message"])

    def test_bls_runtime_secret_is_redacted_from_exception_diagnostics(self):
        secret = "super-secret-bls-key"

        def leaking_fetcher(series_id, label):
            raise RuntimeError(f"upstream rejected key {secret}")

        with patch.dict("os.environ", {"BLS_API_KEY": secret}, clear=False):
            checker = SourceHealthChecker(
                fetchers={"BLS": leaking_fetcher},
                env={"BLS_API_KEY": secret},
                today=date(2026, 8, 29),
            )
            result = checker.check("BLS").to_dict()
        self.assertNotIn(secret, str(result))
        self.assertIn("redacted", result["error_message"])

    def test_provider_subset_can_be_tested_independently(self):
        fetchers = {
            "BLS": lambda series_id, label: evidence("BLS", series_id, "2026-08"),
            "FRED": lambda *args: (_ for _ in ()).throw(AssertionError("not selected")),
            "EIA": lambda *args: (_ for _ in ()).throw(AssertionError("not selected")),
        }
        checker = SourceHealthChecker(fetchers=fetchers, env={}, today=date(2026, 8, 29))
        report = checker.run(["BLS"])
        self.assertTrue(report["ready"])
        self.assertEqual(report["total"], 1)
        self.assertEqual(report["results"][0]["provider"], "BLS")


if __name__ == "__main__":
    unittest.main()
