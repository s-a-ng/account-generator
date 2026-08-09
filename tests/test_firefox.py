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

    def test_existing_account_diagnostic_fails_without_retrying(self):
        calls = 0

        def generate():
            nonlocal calls
            calls += 1
            raise RuntimeError("diagnostic failed")

        with (
            patch.object(firefox, "log"),
            patch.object(firefox, "reauth_diagnostic_username", "disposable-user"),
        ):
            with self.assertRaisesRegex(RuntimeError, "diagnostic failed"):
                firefox.run_loop(generate=generate, max_successes=1)

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


class SessionUploadTests(unittest.TestCase):
    def test_upload_leaves_proxy_assignment_to_the_control_server(self):
        class HbaMaterial:
            @staticmethod
            def upload_payload():
                return {"hba_private_key_jwk": "private-key"}

        class Response:
            status_code = 200
            text = '{"ok":true,"session":{"session_id":"session-1"}}'
            headers = {"content-type": "application/json"}

            @staticmethod
            def json():
                return {"ok": True, "session": {"session_id": "session-1"}}

        with (
            patch.object(firefox, "hba_material", HbaMaterial()),
            patch.object(firefox.requests, "post", return_value=Response()) as post,
            patch.object(firefox, "log"),
        ):
            firefox.upload_session_cookie("cookie-value")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["cookie"], "cookie-value")
        self.assertEqual(payload["hba_private_key_jwk"], "private-key")
        self.assertNotIn("proxy", payload)


class DiagnosticLoginTests(unittest.TestCase):
    def test_diagnostic_username_requires_browser_reauthentication(self):
        with (
            patch.object(firefox, "PASSWORD", "password"),
            patch.object(firefox, "upload_key", "upload-key"),
            patch.object(firefox, "reauth_diagnostic_username", "disposable-user"),
            patch.object(firefox, "browser_reauth_diagnostic", False),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "REAUTH_DIAGNOSTIC_USERNAME requires BROWSER_REAUTH_DIAGNOSTIC",
            ):
                firefox.validate_environment()


if __name__ == "__main__":
    unittest.main()
