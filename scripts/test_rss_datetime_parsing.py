#!/usr/bin/env python3
"""验证 RSS/Atom 时间解析兼容性。"""

import os
import sys
import unittest
from datetime import datetime, timezone


os.environ.setdefault("DOUBAO_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(__file__))

from rss_news_collector import parse_feed_datetime  # noqa: E402


class ParseFeedDatetimeTests(unittest.TestCase):
    def test_parse_rfc2822(self) -> None:
        dt = parse_feed_datetime("Fri, 03 Apr 2026 08:00:00 +0000")
        self.assertEqual(dt, datetime(2026, 4, 3, 8, 0, 0, tzinfo=timezone.utc))

    def test_parse_iso8601_zulu(self) -> None:
        dt = parse_feed_datetime("2026-04-04T15:12:06Z")
        self.assertEqual(dt, datetime(2026, 4, 4, 15, 12, 6, tzinfo=timezone.utc))

    def test_parse_iso8601_offset(self) -> None:
        dt = parse_feed_datetime("2026-04-04T11:00:00-04:00")
        self.assertEqual(dt, datetime.fromisoformat("2026-04-04T11:00:00-04:00"))


if __name__ == "__main__":
    unittest.main()
