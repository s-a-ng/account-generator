import json
import sys
import unittest
from pathlib import Path


GENERATE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "generate"
sys.path.insert(0, str(GENERATE_DIR))

from session_context import HbaMaterial


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


if __name__ == "__main__":
    unittest.main()
