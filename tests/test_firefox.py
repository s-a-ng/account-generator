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


if __name__ == "__main__":
    unittest.main()
