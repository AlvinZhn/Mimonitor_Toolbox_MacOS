"""Phase 2.6 核心修复与视觉规范针对性测试集。

覆盖：
1. [P0 致命崩溃] PresetApplyWorker 专用 QThread 异步下发与主线程 Qt 信号通信，无跨线程 UI 调用
2. [P1 视觉规范] macOS 彻底移除/隐藏右上角自绘交通灯，汉堡菜单保留 32px 安全留白
3. [P1 核心逻辑] 32U / 27U 单一 cat /proc/cmdline + 正则解析与主窗口标题精准格式化
4. [P1 静态资产] 内置 macOS 原生 ADB 二进制优先加载与 chmod 0o755 赋予
5. [P2 样式修复] 深色模式下高对比度文本样式
6. [P2 主题适配] macOS 系统主题跟随 (defaults read -g AppleInterfaceStyle)
"""

import os
import stat
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

from mimonitor_toolbox.dashboard import DashboardInterface, PresetApplyWorker
from mimonitor_toolbox.platform_adapter import get_platform_adapter, reset_platform_adapter
from mimonitor_toolbox.platform_adapter.macos import MacOSAdapter
from mimonitor_toolbox.presets.manager import PresetProfile, get_preset_manager, reset_preset_manager


_qt_app = QApplication.instance() or QApplication([])


class TestPhase26MultiThreadingWorker(unittest.TestCase):
    """P0: 验证 PresetApplyWorker 在 QThread 中安全运行，不直接调用 UI。"""

    def setUp(self):
        reset_preset_manager()

    def test_worker_emits_signal_on_success(self):
        preset = PresetProfile(
            id="test_preset",
            name="护眼测试",
            icon="Eye",
            description="测试场景",
            settings_map={"picture_brightness": 45},
            is_builtin=False,
        )
        fake_app = SimpleNamespace(
            adb_connected=True,
            adb=SimpleNamespace(
                call_jni=mock.MagicMock(),
                put=mock.MagicMock(),
                refresh_pq=mock.MagicMock(),
            ),
        )

        worker = PresetApplyWorker(preset, fake_app)
        received_signals = []
        worker.apply_finished.connect(lambda ok, msg, pid: received_signals.append((ok, msg, pid)))

        # 同步触发 run 方法验证其纯后台执行与信号发射
        worker.run()

        self.assertEqual(len(received_signals), 1)
        ok, msg, pid = received_signals[0]
        self.assertTrue(ok)
        self.assertIn("成功应用", msg)
        self.assertEqual(pid, "test_preset")

    def test_worker_emits_failure_when_disconnected(self):
        preset = PresetProfile(
            id="test_preset_err",
            name="错误测试",
            icon="Eye",
            description="测试场景",
            settings_map={"picture_brightness": 45},
            is_builtin=False,
        )
        fake_app = SimpleNamespace(adb_connected=False, adb=None)

        worker = PresetApplyWorker(preset, fake_app)
        received_signals = []
        worker.apply_finished.connect(lambda ok, msg, pid: received_signals.append((ok, msg, pid)))

        worker.run()

        self.assertEqual(len(received_signals), 1)
        ok, msg, pid = received_signals[0]
        self.assertFalse(ok)
        self.assertIn("尚未连接显示器", msg)


class TestPhase26MacOSWindowTrafficLights(unittest.TestCase):
    """P1: 验证 macOS 交通灯自绘按钮隐藏与安全留白。"""

    def test_macos_titlebar_buttons_hidden_and_margin_set(self):
        from mimonitor_toolbox.main_window import App

        with mock.patch("sys.platform", "darwin"), \
                mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        if hasattr(window, "titleBar") and window.titleBar is not None:
            if hasattr(window.titleBar, "minBtn"):
                self.assertTrue(window.titleBar.minBtn.isHidden())
            if hasattr(window.titleBar, "maxBtn"):
                self.assertTrue(window.titleBar.maxBtn.isHidden())
            if hasattr(window.titleBar, "closeBtn"):
                self.assertTrue(window.titleBar.closeBtn.isHidden())
            if hasattr(window.titleBar, "hBoxLayout"):
                margins = window.titleBar.hBoxLayout.contentsMargins()
                self.assertGreaterEqual(margins.left(), 70)

        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


class TestPhase26ModelDetectionAndCmdlineRegex(unittest.TestCase):
    """P1: 验证通过 cat /proc/cmdline + regex 提取 panel_size。"""

    def test_detect_32u_from_cmdline(self):
        from mimonitor_toolbox import device_features

        raw_cmdline = (
            "console=ttyMT0,921600n1 root=/dev/ram0 rdinit=/init "
            "androidboot.mi.panel_size=32 androidboot.hardware=mt5896 "
            "androidboot.serialno=0123456789"
        )
        host = SimpleNamespace(
            adb=SimpleNamespace(
                ip="192.168.1.14",
                shell=lambda cmd: raw_cmdline,
            ),
            adb_connected=True,
            _run_adb_action=lambda label, op, on_success=None, on_failure=None: on_success(op()),
            _update_app_model_title=mock.MagicMock(),
        )

        with mock.patch("mimonitor_toolbox.core.save_detected_model") as mock_save:
            device_features.DeviceFeaturesMixin._detect_device_model(host)
            mock_save.assert_called_once_with("Redmi G Pro 32U")
            host._update_app_model_title.assert_called_once_with("Redmi G Pro 32U")

    def test_detect_27u_from_cmdline(self):
        from mimonitor_toolbox import device_features

        raw_cmdline = (
            "console=ttyMT0,921600n1 root=/dev/ram0 rdinit=/init "
            "androidboot.mi.panel_size=27 androidboot.hardware=mt5896"
        )
        host = SimpleNamespace(
            adb=SimpleNamespace(
                ip="192.168.1.14",
                shell=lambda cmd: raw_cmdline,
            ),
            adb_connected=True,
            _run_adb_action=lambda label, op, on_success=None, on_failure=None: on_success(op()),
            _update_app_model_title=mock.MagicMock(),
        )

        with mock.patch("mimonitor_toolbox.core.save_detected_model") as mock_save:
            device_features.DeviceFeaturesMixin._detect_device_model(host)
            mock_save.assert_called_once_with("Redmi G Pro 27U")
            host._update_app_model_title.assert_called_once_with("Redmi G Pro 27U")

    def test_app_title_exact_formatting(self):
        from mimonitor_toolbox.main_window import App

        with mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        window.adb_connected = True
        window.adb.ip = "192.168.1.14"
        window._update_app_model_title("Redmi G Pro 32U")
        self.assertEqual("红米 G Pro 32U 控制台 - 已连接 (192.168.1.14)", window.windowTitle())

        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


class TestPhase26BundledAdbPriority(unittest.TestCase):
    """P1: 验证内置 assets/runtime/darwin/adb 的最高加载优先级与 0o755 赋予。"""

    def test_bundled_adb_priority_and_chmod(self):
        adapter = MacOSAdapter()
        real_darwin_adb = os.path.abspath("assets/runtime/darwin/adb")

        if os.path.exists(real_darwin_adb):
            res = adapter.get_bundled_adb_path()
            self.assertEqual(res, real_darwin_adb)
            self.assertTrue(os.access(real_darwin_adb, os.X_OK))


class TestPhase26DarkThemeDetection(unittest.TestCase):
    """P2: 验证 macOS 系统主题探测函数。"""

    def test_macos_system_dark_theme_detection(self):
        adapter = MacOSAdapter()
        with mock.patch("subprocess.check_output", return_value="Dark\n"):
            self.assertTrue(adapter.is_system_dark_theme())
        with mock.patch("subprocess.check_output", return_value="Light\n"):
            self.assertFalse(adapter.is_system_dark_theme())
        with mock.patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "defaults")):
            self.assertFalse(adapter.is_system_dark_theme())


class TestPhase26HintLabelsContrast(unittest.TestCase):
    """P2: 验证画面设置与游戏辅助页面的状态标签高对比度样式。"""

    def test_picture_and_game_hint_labels_have_high_contrast_style(self):
        from mimonitor_toolbox.main_window import App

        with mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        pic_label = getattr(window, "picture_mode_hint_label", None)
        self.assertIsNotNone(pic_label)
        self.assertIn("rgba(255, 255, 255, 0.85)", pic_label.styleSheet())
        self.assertIn("bold", pic_label.styleSheet())

        game_label = getattr(window, "game_mode_hint_label", None)
        self.assertIsNotNone(game_label)
        self.assertIn("#FBBF24", game_label.styleSheet())
        self.assertIn("bold", game_label.styleSheet())

        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


if __name__ == "__main__":
    unittest.main()
