"""测试 CI Webhook 通知模块构造与发送安全逻辑。"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows", "scripts")
sys.path.insert(0, scripts_dir)

import notify


class TestNotifyScript(unittest.TestCase):
    def test_send_webhook_safely_skips_when_url_empty(self):
        with patch.dict(os.environ, {"PUSH_WEBHOOK_URL": ""}):
            result = notify.send_webhook("Title", "Desc", "Content")
            self.assertTrue(result)

    def test_send_webhook_posts_expected_payload(self):
        fake_url = "https://example.com/webhook"
        with patch.dict(os.environ, {"PUSH_WEBHOOK_URL": fake_url}), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"status": "ok"}'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = notify.send_webhook("Title", "Desc", "Content")
            self.assertTrue(result)
            self.assertEqual(mock_urlopen.call_count, 1)

    def test_release_success_formatting(self):
        class Args:
            version = "v3.0.0"
            commit = "abcdef123456"
            release_url = "https://github.com/test/releases/tag/v3.0.0"
            run_url = "https://github.com/test/actions/runs/123"

        title, desc, content = notify.build_release_success_msg(Args())
        self.assertIn("v3.0.0", title)
        self.assertIn("Mimonitor-Toolbox-v3.0.0-macOS.dmg", content)

    def test_build_failure_formatting(self):
        class Args:
            job = "macOS 构建与单测门禁"
            commit = "abcdef123456"
            ref = "refs/heads/master"
            run_url = "https://github.com/test/actions/runs/123"
            error_msg = "测试用例超时"

        title, desc, content = notify.build_build_failure_msg(Args())
        self.assertIn("【紧急报警】需人工接入排查", title)
        self.assertIn("macOS 构建与单测门禁", content)

    def test_upstream_sync_formatting(self):
        class Args:
            behind_count = "3"
            pr_url = "https://github.com/test/pull/1"
            run_url = "https://github.com/test/actions/runs/123"

        title, desc, content = notify.build_upstream_sync_msg(Args())
        self.assertIn("【检测到上游原版新更新】", title)
        self.assertIn("领先 3 个提交", content)
