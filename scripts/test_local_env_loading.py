#!/usr/bin/env python3
"""验证本地私有配置文件加载逻辑。"""

import os
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, os.path.dirname(__file__))

import utils  # noqa: E402


class LocalEnvLoadingTests(unittest.TestCase):
    def test_get_env_var_reads_env_local_without_overriding_existing_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_local = os.path.join(tmpdir, ".env.local")
            with open(env_local, "w", encoding="utf-8") as f:
                f.write("WECHAT_API_KEY=file-key\n")
                f.write("DOUBAO_API_KEY=file-doubao\n")

            with mock.patch.object(utils, "LOCAL_ENV_PATHS", [env_local]), \
                 mock.patch.object(utils, "_LOCAL_ENV_LOADED", False), \
                 mock.patch.dict(os.environ, {"WECHAT_API_KEY": "shell-key"}, clear=True):
                self.assertEqual(utils.get_env_var("WECHAT_API_KEY", required=False), "shell-key")
                self.assertEqual(utils.get_env_var("DOUBAO_API_KEY", required=False), "file-doubao")


if __name__ == "__main__":
    unittest.main()
