#!/usr/bin/env python3
"""验证规则分类兜底逻辑。"""

import os
import sys
import unittest
from unittest import mock


os.environ.setdefault("DOUBAO_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(__file__))

from rss_news_collector import classify_news_with_ai, classify_news_with_rules, infer_item_category  # noqa: E402


class RuleBasedClassificationTests(unittest.TestCase):
    def test_infer_category_prefers_finance_keywords(self) -> None:
        item = {
            "title": "英伟达市值创新高，财报推动股价继续上涨",
            "summary": "公司最新财报和市值变化成为市场焦点",
            "rss_source": "Marketaux",
        }
        self.assertEqual(infer_item_category(item), "财经要闻")

    def test_infer_category_prefers_ai_sources(self) -> None:
        item = {
            "title": "Gemma 4 发布并开放本地部署",
            "summary": "Google DeepMind 推出新模型",
            "rss_source": "Google DeepMind",
        }
        self.assertEqual(infer_item_category(item), "AI 领域")

    def test_rule_classifier_keeps_three_buckets_non_empty(self) -> None:
        news_items = [
            {
                "title": "OpenAI 发布新推理模型并开放 API",
                "summary": "新模型强化复杂任务能力",
                "rss_source": "OpenAI Blog",
                "parsed_time": "2026-04-04 10:00:00",
            },
            {
                "title": "苹果推出新一代 MacBook Air",
                "summary": "新品升级芯片和续航",
                "rss_source": "The Verge",
                "parsed_time": "2026-04-04 09:00:00",
            },
            {
                "title": "特斯拉财报超预期，盘后股价上涨",
                "summary": "营收和利润均好于市场预期",
                "rss_source": "Marketaux",
                "parsed_time": "2026-04-04 08:00:00",
            },
        ]

        categorized = classify_news_with_rules(news_items)
        self.assertEqual(len(categorized["AI 领域"]), 1)
        self.assertEqual(len(categorized["科技动态"]), 1)
        self.assertEqual(len(categorized["财经要闻"]), 1)

    def test_ai_classifier_falls_back_to_rules_when_llm_unavailable(self) -> None:
        news_items = [
            {
                "title": "OpenAI 发布新推理模型并开放 API",
                "summary": "新模型强化复杂任务能力",
                "rss_source": "OpenAI Blog",
                "parsed_time": "2026-04-04 10:00:00",
            },
            {
                "title": "特斯拉财报超预期，盘后股价上涨",
                "summary": "营收和利润均好于市场预期",
                "rss_source": "Marketaux",
                "parsed_time": "2026-04-04 08:00:00",
            },
        ]

        with mock.patch("rss_news_collector.call_llm_api", return_value=None):
            categorized = classify_news_with_ai(news_items)

        self.assertEqual(len(categorized["AI 领域"]), 1)
        self.assertEqual(len(categorized["财经要闻"]), 1)


if __name__ == "__main__":
    unittest.main()
