import json
import sys
import unittest
from pathlib import Path


GENERATE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "generate"
sys.path.insert(0, str(GENERATE_DIR))

from session_context import HbaMaterial, browser_reauthenticate, inspect_hba_keypair


class HbaMaterialTests(unittest.TestCase):
    def test_upload_payload_contains_only_the_required_private_key(self):
        private_key = {
            "kty": "EC",
            "crv": "P-256",
            "d": "private",
            "x": "x",
            "y": "y",
        }
        material = HbaMaterial(
            public_key_spki="public-spki",
            private_key_jwk=private_key,
            public_key_jwk={"kty": "EC", "crv": "P-256", "x": "x", "y": "y"},
            db_name="hbaDB",
            object_store_name="hbaObjectStore",
            key_name="hba_keys",
            db_version=1,
            created_at="2026-08-08T00:00:00Z",
        )

        payload = material.upload_payload()

        self.assertEqual(set(payload), {"hba_private_key_jwk"})
        self.assertEqual(json.loads(payload["hba_private_key_jwk"]), private_key)

    def test_inspection_returns_the_live_indexeddb_key_and_observations(self):
        seeded = HbaMaterial(
            public_key_spki="seeded-public",
            private_key_jwk={"d": "seeded-private"},
            public_key_jwk={"x": "seeded-x"},
            db_name="hbaDB",
            object_store_name="hbaObjectStore",
            key_name="hba_keys",
            db_version=1,
            created_at="2026-08-08T00:00:00Z",
        )

        class Driver:
            def execute_async_script(self, _script, *args):
                self.args = args
                return {
                    "ok": True,
                    "public_key_spki": "live-public",
                    "private_key_jwk": {"d": "live-private"},
                    "public_key_jwk": {"x": "live-x"},
                    "observations": [{"client_public_key": "live-public"}],
                }

        driver = Driver()
        current, observations = inspect_hba_keypair(driver, seeded)

        self.assertEqual(
            driver.args,
            ("hbaDB", "hbaObjectStore", "hba_keys", 1),
        )
        self.assertEqual(current.public_key_spki, "live-public")
        self.assertEqual(current.private_key_jwk, {"d": "live-private"})
        self.assertEqual(current.created_at, seeded.created_at)
        self.assertEqual(observations, [{"client_public_key": "live-public"}])

    def test_browser_reauthentication_returns_sanitized_result(self):
        material = HbaMaterial(
            public_key_spki="public",
            private_key_jwk={"d": "private"},
            public_key_jwk={"x": "x"},
            db_name="hbaDB",
            object_store_name="hbaObjectStore",
            key_name="hba_keys",
            db_version=1,
            created_at="2026-08-08T00:00:00Z",
        )

        class Driver:
            def execute_async_script(self, _script, *args):
                self.args = args
                return {
                    "ok": True,
                    "reauth_status": 200,
                    "authenticated_after_status": 200,
                }

        driver = Driver()
        result = browser_reauthenticate(driver, material)

        self.assertEqual(driver.args, ("public",))
        self.assertEqual(result["reauth_status"], 200)


if __name__ == "__main__":
    unittest.main()
