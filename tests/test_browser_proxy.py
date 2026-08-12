import sys
import unittest
from pathlib import Path


GENERATE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "generate"
sys.path.insert(0, str(GENERATE_DIR))

from browser_proxy import configure_firefox_proxy


class FirefoxProxyConfigurationTests(unittest.TestCase):
    def test_local_bridge_is_used_for_http_and_https(self):
        class Options:
            def __init__(self):
                self.preferences = {}

            def set_preference(self, key, value):
                self.preferences[key] = value

        options = Options()
        configure_firefox_proxy(options, "http://127.0.0.1:32123")

        self.assertEqual(options.preferences["network.proxy.type"], 1)
        self.assertEqual(options.preferences["network.proxy.http"], "127.0.0.1")
        self.assertEqual(options.preferences["network.proxy.http_port"], 32123)
        self.assertEqual(options.preferences["network.proxy.ssl"], "127.0.0.1")
        self.assertEqual(options.preferences["network.proxy.ssl_port"], 32123)


if __name__ == "__main__":
    unittest.main()
