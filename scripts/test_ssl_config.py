#!/usr/bin/env python3
"""验证微信发布接口的 SSL 配置解析。"""

import os
import sys
import unittest
from unittest import mock


sys.path.insert(0, os.path.dirname(__file__))

import auto_daily_news as mod  # noqa: E402


class SslConfigTests(unittest.TestCase):
    def test_parse_bool_env(self) -> None:
        self.assertTrue(mod.parse_bool_env("true"))
        self.assertTrue(mod.parse_bool_env("1"))
        self.assertFalse(mod.parse_bool_env("false"))
        self.assertFalse(mod.parse_bool_env("0"))

    def test_resolve_ssl_verify_false(self) -> None:
        with mock.patch.object(mod, "get_env_var", side_effect=lambda name, **kwargs: "false" if name == "WECHAT_SSL_VERIFY" else None):
            self.assertFalse(mod.resolve_ssl_verify())

    def test_resolve_ssl_verify_ca_bundle(self) -> None:
        def fake_get_env_var(name, **kwargs):
            if name == "WECHAT_SSL_VERIFY":
                return "true"
            if name == "WECHAT_CA_BUNDLE":
                return "/tmp/custom-ca.pem"
            return None

        with mock.patch.object(mod, "get_env_var", side_effect=fake_get_env_var):
            self.assertEqual(mod.resolve_ssl_verify(), "/tmp/custom-ca.pem")


if __name__ == "__main__":
    unittest.main()
