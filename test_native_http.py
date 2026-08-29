import ssl
import unittest

from native_http import system_ssl_context


class NativeHTTPTests(unittest.TestCase):
    def test_system_context_keeps_certificate_verification_enabled(self):
        context = system_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


if __name__ == "__main__":
    unittest.main()
