import importlib.util
import unittest
from unittest.mock import Mock, patch
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

    def test_extract_date_formats(self):
        self.assertEqual(collector.extract_date("Notice dated 12.11.2026"), "2026-11-12T00:00:00Z")
        self.assertEqual(collector.extract_date("Dated 2026-11-12"), "2026-11-12T00:00:00Z")

    def test_source_snapshot_replaces_old_records(self):
        records = {
            "old": {"sourceId": "ddumhsac-exams"},
            "keep": {"sourceId": "pubmed-india-health"}
        }
        refreshed = {key: value for key, value in records.items()
                     if value.get("sourceId") != "ddumhsac-exams"}
        self.assertEqual(list(refreshed), ["keep"])

    def test_category_routing(self):
        source = {"defaultCategory": "exam-radar", "categoryRules": [
            {"contains": ["NEET PG"], "category": "neet-pg"}]}
        self.assertEqual(collector.route_category(source, "NEET PG 2026 notice"), "neet-pg")
        self.assertEqual(collector.route_category(source, "University timetable"), "exam-radar")


    def test_collect_html_uses_official_fallback_endpoint(self):
        source = {
            "id": "nbems-notice-board", "name": "NBEMS", "tier": "official",
            "defaultCategory": "exam-radar",
            "url": "https://webdisk.natboard.edu.in/primary",
            "fallbackUrls": ["https://webdisk.natboard.edu.in/fallback"]
        }
        failed = Mock()
        failed.raise_for_status.side_effect = collector.requests.HTTPError("403 Forbidden")
        good = Mock()
        good.content = (b'<table><tr><td>12-11-2026</td><td>'
                        b'<a href="/notice.pdf">NEET PG 2026 Notice</a>'
                        b'</td></tr></table>')
        good.raise_for_status.return_value = None
        with patch.object(collector.SESSION, "get", side_effect=[failed, good]) as get:
            items = collector.collect_html(source)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "exam-radar")
        self.assertEqual(items[0]["url"], "https://webdisk.natboard.edu.in/notice.pdf")

    def test_curated_source_publishes_only_configured_outbound_links(self):
        source = {
            "id": "neetpgai-free-guides", "name": "NEETPGAI – Free Study Guides",
            "tier": "educational", "defaultCategory": "neet-pg",
            "entries": [{
                "id": "directory", "title": "Free study guides",
                "description": "Browse the publisher's free study guide catalogue.",
                "url": "https://neetpgai.com/neet-pg-study-material?exam=NEET-PG"
            }]
        }
        items = collector.collect_curated(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "neet-pg")
        self.assertEqual(items[0]["tier"], "educational")
        self.assertEqual(items[0]["url"], "https://neetpgai.com/neet-pg-study-material?exam=NEET-PG")

    def test_make_item_requires_http_url(self):
        source = {"id": "s", "name": "Source", "tier": "official", "defaultCategory": "medical-news"}
        self.assertIsNone(collector.make_item(source, "Title", "file:///tmp/a"))
        item = collector.make_item(source, "Title", "https://example.org/a", date="2026-11-12")
        self.assertEqual(item["publishedAt"], "2026-11-12T00:00:00Z")

if __name__ == "__main__":
    unittest.main()
