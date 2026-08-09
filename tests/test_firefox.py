import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


GENERATE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "generate"
sys.path.insert(0, str(GENERATE_DIR))

os.environ.setdefault("AGE_VERIFICATION_ENABLED", "false")

import firefox


class GeneratorLoopTests(unittest.TestCase):
    def test_captcha_is_a_clean_stop_after_completed_accounts(self):
        outcomes = iter([True, True, firefox.CaptchaDetected("challenge")])

        def generate():
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with patch.object(firefox, "log"):
            self.assertEqual(firefox.run_loop(generate=generate, max_successes=0), 2)

    def test_captcha_is_a_clean_stop_before_the_first_account(self):
        def generate():
            raise firefox.CaptchaDetected("challenge")

        with patch.object(firefox, "log"):
            self.assertEqual(firefox.run_loop(generate=generate, max_successes=0), 0)

    def test_canary_success_limit_bounds_the_worker(self):
        calls = 0

        def generate():
            nonlocal calls
            calls += 1
            return True

        with patch.object(firefox, "log"):
            self.assertEqual(firefox.run_loop(generate=generate, max_successes=3), 3)
        self.assertEqual(calls, 3)

    def test_retry_limit_still_fails_non_captcha_errors(self):
        def generate():
            raise RuntimeError("broken")

        with (
            patch.object(firefox, "log"),
            patch.object(firefox, "generator_retry_attempts", 2),
        ):
            with self.assertRaisesRegex(RuntimeError, "Exceeded 2 generator retries"):
                firefox.run_loop(generate=generate, max_successes=0)

    def test_import_failure_does_not_create_another_account(self):
        calls = 0

        def generate():
            nonlocal calls
            calls += 1
            raise firefox.SessionImportFailed("rejected")

        with patch.object(firefox, "log"):
            with self.assertRaisesRegex(firefox.SessionImportFailed, "rejected"):
                firefox.run_loop(generate=generate, max_successes=0)

        self.assertEqual(calls, 1)


class ImportStatusUrlTests(unittest.TestCase):
    def test_same_host_status_url_uses_the_configured_https_scheme(self):
        with patch.object(
            firefox,
            "upload_url",
            "https://command.botted.org/api/internal/roblox-sessions/import",
        ):
            self.assertEqual(
                firefox.import_status_url({
                    "id": "job-1",
                    "status_url": "http://command.botted.org/api/internal/roblox-sessions/import-status?job_id=job-1",
                }),
                "https://command.botted.org/api/internal/roblox-sessions/import-status?job_id=job-1",
            )

    def test_missing_status_url_is_derived_from_the_job_id(self):
        with patch.object(
            firefox,
            "upload_url",
            "https://command.botted.org/api/internal/roblox-sessions/import",
        ):
            self.assertEqual(
                firefox.import_status_url({"id": "job id"}),
                "https://command.botted.org/api/internal/roblox-sessions/import-status?job_id=job+id",
            )


class ImportProxyTests(unittest.TestCase):
    def test_proxy_endpoint_is_derived_from_the_upload_origin(self):
        with patch.object(
            firefox,
            "upload_url",
            "https://command.botted.org/api/internal/roblox-sessions/import",
        ):
            self.assertEqual(
                firefox.control_endpoint("/api/internal/roblox-sessions/import-proxy"),
                "https://command.botted.org/api/internal/roblox-sessions/import-proxy",
            )

    def test_acquired_proxy_is_returned_without_logging_credentials(self):
        class Response:
            status_code = 200
            text = '{"ok":true,"proxy":"socks5://user:pass@example.test:1080"}'
            headers = {"content-type": "application/json"}

            @staticmethod
            def json():
                return {"ok": True, "proxy": "socks5://user:pass@example.test:1080"}

        with (
            patch.object(firefox.requests, "post", return_value=Response()),
            patch.object(firefox, "log") as log,
        ):
            proxy = firefox.acquire_import_proxy()

        self.assertEqual(proxy, "socks5://user:pass@example.test:1080")
        logged_fields = log.call_args.kwargs
        self.assertNotIn("user", str(logged_fields))
        self.assertNotIn("pass", str(logged_fields))
        self.assertEqual(logged_fields["proxy"]["has_auth"], True)

    def test_split_host_port_accepts_ipv4_hostname_and_ipv6(self):
        self.assertEqual(firefox.split_host_port("example.test:8080", 80), ("example.test", 8080))
        self.assertEqual(firefox.split_host_port("example.test", 80), ("example.test", 80))
        self.assertEqual(firefox.split_host_port("[2001:db8::1]:8443", 443), ("2001:db8::1", 8443))

    def test_firefox_uses_the_local_bridge_for_http_and_https(self):
        class Options:
            def __init__(self):
                self.preferences = {}

            def set_preference(self, key, value):
                self.preferences[key] = value

        options = Options()
        firefox.configure_firefox_proxy(options, "http://127.0.0.1:32123")

        self.assertEqual(options.preferences["network.proxy.type"], 1)
        self.assertEqual(options.preferences["network.proxy.http"], "127.0.0.1")
        self.assertEqual(options.preferences["network.proxy.http_port"], 32123)
        self.assertEqual(options.preferences["network.proxy.ssl"], "127.0.0.1")
        self.assertEqual(options.preferences["network.proxy.ssl_port"], 32123)


if __name__ == "__main__":
    unittest.main()
