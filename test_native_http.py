import ssl
import unittest
from http.client import RemoteDisconnected
from unittest.mock import MagicMock, patch

from native_http import http_get_text, system_ssl_context


class NativeHTTPTests(unittest.TestCase):
    def test_system_context_keeps_certificate_verification_enabled(self):
        context = system_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_text_transport_uses_verified_system_context(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"\xef\xbb\xbfDATE,DGS2\n2026-01-02,4.00\n"
        context = MagicMock()
        with patch("native_http.system_ssl_context", return_value=context), patch(
            "native_http.urlopen", return_value=response
        ) as mocked_open:
            text = http_get_text("https://fred.example/data.csv", accept="text/csv")
        self.assertTrue(text.startswith("DATE,DGS2"))
        self.assertIs(mocked_open.call_args.kwargs["context"], context)
        self.assertEqual(mocked_open.call_args.kwargs["timeout"], 20)

    def test_text_transport_normalizes_remote_disconnect_for_runtime_retry(self):
        with patch("native_http.system_ssl_context", return_value=MagicMock()), patch(
            "native_http.urlopen",
            side_effect=RemoteDisconnected("Remote end closed connection without response"),
        ):
            with self.assertRaisesRegex(
                ConnectionError,
                "RemoteDisconnected: Remote end closed connection without response",
            ):
                http_get_text("https://fred.example/data.csv", accept="text/csv")


if __name__ == "__main__":
    unittest.main()
