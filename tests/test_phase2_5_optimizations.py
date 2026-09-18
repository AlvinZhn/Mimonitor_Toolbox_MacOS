import os
import sys
import unittest
from unittest import mock
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

_qt_app = QApplication.instance() or QApplication(["test", "-platform", "offscreen"])


class TestVisualAndButtonOptimizations(unittest.TestCase):
    """测试界面文字截断防护与 TagBadge 样式。"""

    def test_preset_card_apply_button_width(self):
        from mimonitor_toolbox.presets.manager import PresetProfile
        from mimonitor_toolbox.dashboard import PresetCard, TagBadge

        profile = PresetProfile(
            id="test_profile",
            name="测试模式",
            icon="PALETTE",
            description="描述文字",
            is_builtin=False,
            settings_map={"backlight": 50, "picture_local_dimming": 1},
        )
        card = PresetCard(profile)
        # 验证最小宽度不低于 96px，确保 macOS/高 DPI 下不截断
        self.assertGreaterEqual(card.apply_btn.minimumWidth(), 96)
        card.deleteLater()
        _qt_app.processEvents()

    def test_tag_badge_contrast_styling(self):
        from mimonitor_toolbox.dashboard import TagBadge

        badge = TagBadge("背光 80%")
        ss = badge.styleSheet()
        self.assertIn("rgba(255, 255, 255, 0.12)", ss)
        self.assertIn("#FFFFFF", ss)
        badge.deleteLater()
        _qt_app.processEvents()

    def test_remote_page_volume_buttons_width(self):
        from PyQt6.QtWidgets import QAbstractButton
        from mimonitor_toolbox.main_window import App

        with mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        # 查找遥控器页面的三个核心音量控制按键
        vol_buttons = [
            btn for btn in window.remote_page.findChildren(QAbstractButton)
            if any(text in btn.text() for text in ["音量-", "静音", "音量+"])
        ]
        self.assertGreaterEqual(len(vol_buttons), 3)
        for btn in vol_buttons:
            self.assertGreaterEqual(btn.width(), 80)
        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


class TestMacTitleBarTrafficLights(unittest.TestCase):
    """测试 macOS 平台下标题栏红黄绿交通灯位置与按钮消除。"""

    def test_macos_titlebar_margins_and_hidden_buttons(self):
        from mimonitor_toolbox.main_window import App

        with mock.patch("sys.platform", "darwin"), \
                mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        if hasattr(window, "titleBar") and window.titleBar is not None:
            # 验证右上角按钮已隐藏
            self.assertTrue(window.titleBar.minBtn.isHidden())
            self.assertTrue(window.titleBar.maxBtn.isHidden())
            self.assertTrue(window.titleBar.closeBtn.isHidden())
            # 验证左侧为交通灯预留 70px 边距
            margins = window.titleBar.hBoxLayout.contentsMargins()
            self.assertGreaterEqual(margins.left(), 70)

        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


class TestMacAdbTerminalAlternative(unittest.TestCase):
    """测试 macOS 平台下 ADB CMD 与 Shell 调起 Terminal.app。"""

    def test_open_adb_cmd_on_macos_triggers_terminal_script(self):
        from mimonitor_toolbox import device_features

        messages = []
        host = SimpleNamespace(
            adb=SimpleNamespace(ip="192.168.1.100"),
            adb_connected=True,
            log=messages.append,
            _show_message_box=mock.MagicMock(),
        )

        with mock.patch("sys.platform", "darwin"), \
                mock.patch("subprocess.Popen") as mock_popen:
            device_features.DeviceFeaturesMixin._open_adb_cmd(host)

        self.assertTrue(mock_popen.called)
        args, _ = mock_popen.call_args
        self.assertEqual(args[0][0], "osascript")
        self.assertEqual(args[0][1], "-e")
        self.assertIn('tell application "Terminal" to activate do script', args[0][2])
        # 验证绝无弹出“仅支持 Windows”的错误对话框
        host._show_message_box.assert_not_called()

    def test_open_shell_on_macos_triggers_terminal_script(self):
        from mimonitor_toolbox import device_features

        messages = []
        host = SimpleNamespace(
            adb=SimpleNamespace(ip="192.168.1.100"),
            adb_connected=True,
            log=messages.append,
            _show_message_box=mock.MagicMock(),
        )

        with mock.patch("sys.platform", "darwin"), \
                mock.patch("subprocess.Popen") as mock_popen:
            device_features.DeviceFeaturesMixin._open_shell(host)

        self.assertTrue(mock_popen.called)
        args, _ = mock_popen.call_args
        self.assertEqual(args[0][0], "osascript")
        self.assertIn('tell application "Terminal" to activate do script', args[0][2])
        self.assertIn("192.168.1.100:5555 shell", args[0][2])


class TestModelDetectionAndDynamicTitle(unittest.TestCase):
    """测试 27U/32U 面板尺寸动态识别与命名持久化。"""

    def test_cached_model_title_defaults_and_formatting(self):
        from mimonitor_toolbox.core import get_cached_model_title, save_detected_model, DEFAULT_APP_TITLE

        with mock.patch("mimonitor_toolbox.core.load_settings", return_value={"detected_model": None}):
            self.assertEqual(get_cached_model_title(), DEFAULT_APP_TITLE)

        with mock.patch("mimonitor_toolbox.core.load_settings", return_value={"detected_model": "Redmi G Pro 32U"}):
            self.assertEqual(get_cached_model_title(), "红米 G Pro 32U 控制台")

        with mock.patch("mimonitor_toolbox.core.load_settings", return_value={"detected_model": "Redmi G Pro 27U"}):
            self.assertEqual(get_cached_model_title(), "红米 G Pro 27U 控制台")

    def test_detect_device_model_parses_32u_panel(self):
        from mimonitor_toolbox import device_features

        host = SimpleNamespace(
            adb=SimpleNamespace(
                ip="192.168.1.100",
                shell=lambda cmd: "console=ttyS0 androidboot.mi.panel_size=32 init=/init\n",
            ),
            adb_connected=True,
            model_detected_signal=SimpleNamespace(emit=mock.MagicMock()),
            _update_app_model_title=mock.MagicMock(),
        )

        with mock.patch("mimonitor_toolbox.core.save_detected_model") as mock_save, \
             mock.patch("mimonitor_toolbox.device_features.async_run", side_effect=lambda fn: fn()):
            device_features.DeviceFeaturesMixin._detect_device_model(host)
            mock_save.assert_called_once_with("Redmi G Pro 32U")
            host.model_detected_signal.emit.assert_called_once_with("Redmi G Pro 32U")

    def test_detect_device_model_parses_27u_panel(self):
        from mimonitor_toolbox import device_features

        host = SimpleNamespace(
            adb=SimpleNamespace(
                ip="192.168.1.100",
                shell=lambda cmd: "console=ttyS0 androidboot.mi.panel_size=27 init=/init\n",
            ),
            adb_connected=True,
            model_detected_signal=SimpleNamespace(emit=mock.MagicMock()),
            _update_app_model_title=mock.MagicMock(),
        )

        with mock.patch("mimonitor_toolbox.core.save_detected_model") as mock_save, \
             mock.patch("mimonitor_toolbox.device_features.async_run", side_effect=lambda fn: fn()):
            device_features.DeviceFeaturesMixin._detect_device_model(host)
            mock_save.assert_called_once_with("Redmi G Pro 27U")
            host.model_detected_signal.emit.assert_called_once_with("Redmi G Pro 27U")

    def test_update_app_model_title_updates_window_and_tray(self):
        from mimonitor_toolbox.main_window import App

        with mock.patch.object(App, "register_global_hotkeys"), \
                mock.patch.object(App, "setup_tray"):
            window = App()

        window.adb_connected = True
        window.adb.ip = "192.168.1.14"
        window.tray_icon = mock.MagicMock()
        window._update_app_model_title("Redmi G Pro 32U")
        self.assertEqual("红米 G Pro 32U 控制台 - 已连接 (192.168.1.14)", window.windowTitle())
        window.tray_icon.setToolTip.assert_called_with("红米 G Pro 32U 控制台")
        self.assertEqual(window.home_title_label.text(), "红米 G Pro 32U 控制台")

        window._cleanup_done = True
        window.deleteLater()
        _qt_app.processEvents()


if __name__ == "__main__":
    unittest.main()
