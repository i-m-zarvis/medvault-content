import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collector", ROOT / "scripts/collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

class CollectorTests(unittest.TestCase):
    def test_stable_ids(self):
        self.assertEqual(collector.stable_id("src", "123"), collector.stable_id("src", "123"))
        self.assertNotEqual(collector.stable_id("src", "123"), collector.stable_id("src", "456"))

    def test_safe_url(self):
        self.assertIsNone(collector.safe_url("javascript:alert(1)"))
        self.assertEqual(collector.safe_url("https://example.org/a"), "https://example.org/a")

    def test_clean_whitespace(self):
        self.assertEqual(collector.clean("  beta\n  blocker "), "beta blocker")

    def test_make_item_requires_http_url(self):
        source = {"id": "s", "name": "Source", "tier": "official", "defaultCategory": "medical-news"}
        self.assertIsNone(collector.make_item(source, "Title", "file:///tmp/a"))
        item = collector.make_item(source, "Title", "https://example.org/a", date="2026-11-12")
        self.assertEqual(item["publishedAt"], "2026-11-12T00:00:00Z")

if __name__ == "__main__":
    unittest.main()
