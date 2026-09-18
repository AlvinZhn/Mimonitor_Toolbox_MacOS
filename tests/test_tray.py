"""测试系统托盘菜单增强、macOS 模板图标与情景模式快捷切换逻辑。"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from mimonitor_toolbox.main_window import App
from mimonitor_toolbox.presets.manager import get_preset_manager


class TestTrayFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication(["test", "-platform", "offscreen"])

    def setUp(self):
        # 全面屏蔽所有可能开辟线程或原生弹窗的后台逻辑
        self._patchers = [
            patch.object(App, "initialize_display_features", lambda self: None),
            patch.object(App, "register_global_hotkeys", lambda self: None),
            patch.object(App, "_auto_connect_on_startup", lambda self: None),
            patch("PyQt6.QtCore.QTimer.singleShot", lambda *args, **kwargs: None),
            patch("PyQt6.QtWidgets.QSystemTrayIcon.showMessage", MagicMock()),
            patch("mimonitor_toolbox.dashboard.PresetApplyWorker.start", MagicMock()),
        ]
        for p in self._patchers:
            p.start()

        self.app = App()
        # 停止所有后台轮询定时器，确保无头环境下绝对安全受控
        for timer_name in ("adb_keepalive_timer", "adb_server_monitor_timer", "hdr_memory_timer"):
            timer = getattr(self.app, timer_name, None)
            if timer:
                timer.stop()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.cleanup_before_exit()
            self.app.deleteLater()
        for p in reversed(self._patchers):
            p.stop()

    def test_tray_icon_and_menu_created(self):
        """测试托盘图标与右键菜单是否正确创建并挂载。"""
        self.assertIsNotNone(self.app.tray_icon)
        self.assertIsNotNone(self.app.tray_menu)
        if sys.platform == "darwin":
            # macOS 下托盘图标应设置为 Template/Mask
            self.assertTrue(self.app.tray_icon.icon().isMask())

    def test_update_tray_menu_actions(self):
        """测试托盘菜单项动态生成与当前激活项前缀标识。"""
        mgr = get_preset_manager()
        mgr.set_active_preset_id("office_eyecare")

        self.app._update_tray_menu()
        actions = self.app.tray_menu.actions()

        action_texts = [a.text() for a in actions if not a.isSeparator()]
        self.assertIn("显示主窗口", action_texts)
        self.assertIn("退出程序", action_texts)

        # 检查预设是否存在，且 active 预设前缀为 "● "，其它为 "   "
        self.assertTrue(any("● 办公护眼" in t for t in action_texts))
        self.assertTrue(any("320Hz电竞" in t and "●" not in t for t in action_texts))

    def test_apply_preset_from_tray_disconnected(self):
        """测试未连接显示器时点击托盘情景能够安全拦截并弹出轻提示，严禁开辟线程或产生阻塞。"""
        self.app.adb_connected = False
        with patch.object(self.app.tray_icon, "showMessage") as mock_msg, \
             patch("mimonitor_toolbox.dashboard.PresetApplyWorker.start") as mock_worker_start:
            self.app._apply_preset_from_tray("office_eyecare")
            mock_msg.assert_called_once()
            self.assertIn("尚未连接显示器", mock_msg.call_args[0][1])
            mock_worker_start.assert_not_called()

    def test_apply_preset_from_tray_connected_dispatches_worker(self):
        """测试已连接状态下点击情景会安全构建并启动 PresetApplyWorker，且线程 start 处于 Mock 拦截状态。"""
        self.app.adb_connected = True
        self.app.adb = MagicMock()
        mgr = get_preset_manager()
        mgr._is_applying = False

        with patch.object(self.app.tray_icon, "showMessage") as mock_msg, \
             patch("mimonitor_toolbox.dashboard.PresetApplyWorker.start") as mock_worker_start:
            self.app._apply_preset_from_tray("office_eyecare")
            mock_worker_start.assert_called_once()
            mock_msg.assert_called_once()
            self.assertIn("正在切换至", mock_msg.call_args[0][1])

    def test_apply_preset_from_tray_success_callback(self):
        """测试托盘下发完成回调后，同步刷新菜单与主窗口。"""
        with patch.object(self.app.tray_icon, "showMessage") as mock_msg, \
             patch.object(self.app, "_sync_ui_from_preset") as mock_sync, \
             patch.object(self.app, "_update_tray_menu") as mock_update:
            self.app._on_tray_preset_applied(True, "应用成功", "office_eyecare")
            mock_msg.assert_called_once()
            self.assertIn("情景切换完成", mock_msg.call_args[0][0])
            mock_sync.assert_called_once()
            mock_update.assert_called_once()
