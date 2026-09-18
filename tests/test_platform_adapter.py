"""Platform Adapter 跨平台抽象层单元测试 (Phase 1 闸门测试)。"""

from __future__ import annotations

import os
import plistlib
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from mimonitor_toolbox.platform_adapter import (
    BasePlatformAdapter,
    FallbackAdapter,
    MacOSAdapter,
    WindowsAdapter,
    get_platform_adapter,
    reset_platform_adapter,
)


class PlatformAdapterFactoryTests(unittest.TestCase):
    """验证平台适配器单例加载与跨平台模拟。"""

    def tearDown(self):
        reset_platform_adapter()

    def test_current_platform_loads_proper_adapter(self):
        adapter = get_platform_adapter()
        self.assertIsInstance(adapter, BasePlatformAdapter)
        if sys.platform == "darwin":
            self.assertIsInstance(adapter, MacOSAdapter)
        elif sys.platform == "win32":
            self.assertIsInstance(adapter, WindowsAdapter)

    def test_singleton_behavior(self):
        adapter1 = get_platform_adapter()
        adapter2 = get_platform_adapter()
        self.assertIs(adapter1, adapter2)

    def test_linux_simulated_platform_loads_fallback_adapter(self):
        reset_platform_adapter()
        with mock.patch.object(sys, "platform", "linux"):
            adapter = get_platform_adapter()
            self.assertIsInstance(adapter, FallbackAdapter)
            self.assertFalse(adapter.get_hdr_state())
            self.assertFalse(adapter.register_global_hotkey("Ctrl + Alt + F1", lambda: None))
            self.assertFalse(adapter.set_autostart(True))
            self.assertIsNone(adapter.get_autostart_path())

    def test_windows_simulated_platform_loads_windows_adapter(self):
        reset_platform_adapter()
        with mock.patch.object(sys, "platform", "win32"):
            adapter = get_platform_adapter()
            self.assertIsInstance(adapter, WindowsAdapter)


class MacOSAdapterHdrTests(unittest.TestCase):
    """验证 macOS 下 HDR 检测不会抛出 ImportError 或 DLL 缺失，并能正确判定。"""

    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_hdr_state_does_not_raise_or_crash_on_any_environment(self):
        state = self.adapter.get_hdr_state()
        self.assertIsInstance(state, bool)

    def test_hdr_state_true_when_screen_edr_greater_than_one(self):
        fake_screen = SimpleNamespace(
            maximumExtendedDynamicRangeColorComponentValue=lambda: 2.0
        )
        fake_appkit = SimpleNamespace(
            NSScreen=SimpleNamespace(screens=lambda: [fake_screen])
        )
        with mock.patch.dict("sys.modules", {"AppKit": fake_appkit}):
            self.assertTrue(self.adapter.get_hdr_state())

    def test_hdr_state_false_when_screen_edr_is_one(self):
        fake_screen = SimpleNamespace(
            maximumExtendedDynamicRangeColorComponentValue=lambda: 1.0
        )
        fake_appkit = SimpleNamespace(
            NSScreen=SimpleNamespace(screens=lambda: [fake_screen])
        )
        with mock.patch.dict("sys.modules", {"AppKit": fake_appkit}):
            self.assertFalse(self.adapter.get_hdr_state())

    def test_hdr_state_handles_import_error_gracefully(self):
        with mock.patch.dict("sys.modules", {"AppKit": None}):
            state = self.adapter.get_hdr_state()
            self.assertFalse(state)


class MacOSAdapterNetworkFilteringTests(unittest.TestCase):
    """验证 macOS 虚拟网卡过滤与物理网卡识别。"""

    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_filters_virtual_interfaces_from_string_list(self):
        interfaces = [
            "en0",
            "utun0",
            "utun1024",
            "awdl0",
            "bridge0",
            "bridge100",
            "llw0",
            "lo0",
            "gif0",
            "stf0",
            "anpi0",
            "vmenet0",
            "en1",
            "en4",
        ]
        filtered = self.adapter.filter_physical_interfaces(interfaces)
        self.assertEqual(filtered, ["en0", "en1", "en4"])

    def test_filters_virtual_interfaces_from_object_list(self):
        interfaces = [
            SimpleNamespace(interface_name="en0"),
            SimpleNamespace(interface_name="utun0"),
            SimpleNamespace(interface_name="bridge0"),
            SimpleNamespace(interface_name="awdl0"),
            SimpleNamespace(interface_name="en5"),
        ]
        filtered = self.adapter.filter_physical_interfaces(interfaces)
        names = [item.interface_name for item in filtered]
        self.assertEqual(names, ["en0", "en5"])

    def test_filters_virtual_interfaces_from_dict_list(self):
        interfaces = [
            {"name": "en0"},
            {"name": "utun1"},
            {"name": "bridge100"},
            {"name": "en6"},
        ]
        filtered = self.adapter.filter_physical_interfaces(interfaces)
        names = [item["name"] for item in filtered]
        self.assertEqual(names, ["en0", "en6"])


class MacOSAdapterAdbPathTests(unittest.TestCase):
    """验证 ADB 路径适配、内置 ADB 优先与权限设置。"""

    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_prefers_bundled_darwin_adb_and_ensures_chmod_x(self):
        if sys.platform == "win32":
            self.skipTest("Windows 文件系统不具备 POSIX X_OK 权限位，跳过此测试")

        with tempfile.TemporaryDirectory() as temp_dir:
            darwin_dir = os.path.join(temp_dir, "assets", "runtime", "darwin")
            os.makedirs(darwin_dir, exist_ok=True)
            fake_adb = os.path.join(darwin_dir, "adb")
            with open(fake_adb, "w") as f:
                f.write("#!/bin/sh\necho fake adb\n")

            # 初始移除执行权限
            os.chmod(fake_adb, stat.S_IRUSR | stat.S_IWUSR)
            self.assertFalse(os.access(fake_adb, os.X_OK))

            with mock.patch(
                "mimonitor_toolbox.core.bundled_resource_path",
                return_value=fake_adb,
            ):
                result_path = self.adapter.get_bundled_adb_path()
                self.assertEqual(result_path, fake_adb)
                # 验证已自动添加执行权限 (chmod 0o755)
                self.assertTrue(os.access(fake_adb, os.X_OK))

    def test_prefers_system_path_when_bundled_absent_and_which_adb_found(self):
        orig_exists = os.path.exists
        darwin_adb_marker = os.path.join("darwin", "adb")
        with mock.patch("mimonitor_toolbox.core.bundled_resource_path", return_value=None), \
             mock.patch("os.path.exists", side_effect=lambda p: False if (darwin_adb_marker in str(p) or "darwin/adb" in str(p).replace("\\", "/")) else orig_exists(p)), \
             mock.patch("shutil.which", return_value="/opt/homebrew/bin/adb"):
            self.assertEqual(self.adapter.get_bundled_adb_path(), "/opt/homebrew/bin/adb")

    def test_is_system_dark_theme_detects_dark_and_light(self):
        with mock.patch("subprocess.check_output", return_value="Dark\n"):
            self.assertTrue(self.adapter.is_system_dark_theme())
        with mock.patch("subprocess.check_output", side_effect=Exception("error")):
            self.assertFalse(self.adapter.is_system_dark_theme())

    def test_prefers_user_cached_adb_when_present(self):
        user_adb = os.path.expanduser("~/.mimonitor_toolbox/bin/adb")
        orig_exists = os.path.exists
        darwin_adb_marker = os.path.join("darwin", "adb")
        with mock.patch("shutil.which", return_value=None), mock.patch(
            "mimonitor_toolbox.core.bundled_resource_path",
            return_value=None,
        ), mock.patch(
            "os.path.exists",
            side_effect=lambda p: (os.path.normpath(str(p)) == os.path.normpath(str(user_adb))) if (darwin_adb_marker not in str(p) and "darwin/adb" not in str(p).replace("\\", "/")) else False,
        ), mock.patch(
            "os.access", return_value=True
        ):
            self.assertEqual(os.path.normpath(self.adapter.get_bundled_adb_path()), os.path.normpath(user_adb))

    def test_returns_plain_adb_when_resource_does_not_exist(self):
        with mock.patch("shutil.which", return_value=None), mock.patch(
            "mimonitor_toolbox.core.bundled_resource_path",
            return_value=None,
        ), mock.patch(
            "os.path.exists",
            return_value=False,
        ), mock.patch.object(
            self.adapter,
            "_bootstrap_adb_binary",
            return_value=False,
        ):
            self.assertEqual(self.adapter.get_bundled_adb_path(), "adb")


class MacOSAdapterHotkeyDegradationTests(unittest.TestCase):
    """验证辅助功能权限检测与优雅降级。"""

    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_degrades_gracefully_when_not_trusted(self):
        called = False

        def on_pressed():
            nonlocal called
            called = True

        with mock.patch.object(self.adapter, "is_accessibility_trusted", return_value=False):
            # 未授权时不抛出任何异常，优雅返回 False 并标记降级
            res = self.adapter.register_global_hotkey("Ctrl + Alt + F1", on_pressed)
            self.assertFalse(res)
            self.assertTrue(self.adapter.is_hotkey_degraded())

            # 窗口聚焦本地热键仍被成功登记
            handler = self.adapter.get_window_hotkey_handler("Ctrl + Alt + F1")
            self.assertIsNotNone(handler)
            handler()
            self.assertTrue(called)

    def test_unregister_clears_handlers_and_degraded_state(self):
        with mock.patch.object(self.adapter, "is_accessibility_trusted", return_value=False):
            self.adapter.register_global_hotkey("Ctrl + Alt + F2", lambda: None)
            self.assertTrue(self.adapter.is_hotkey_degraded())
            self.adapter.unregister_all_hotkeys()
            self.assertFalse(self.adapter.is_hotkey_degraded())
            self.assertIsNone(self.adapter.get_window_hotkey_handler("Ctrl + Alt + F2"))


class MacOSAdapterAutostartTests(unittest.TestCase):
    """验证 macOS LaunchAgent 开机自启生成与删除。"""

    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_autostart_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plist_path = os.path.join(temp_dir, "test.plist")
            with mock.patch.object(self.adapter, "get_autostart_path", return_value=plist_path):
                # 开启自启
                res = self.adapter.set_autostart(True, executable="/usr/local/bin/myapp")
                self.assertTrue(res)
                self.assertTrue(os.path.exists(plist_path))

                with open(plist_path, "rb") as f:
                    data = plistlib.load(f)
                    self.assertEqual(data["Label"], "com.mimonitor.toolbox")
                    self.assertEqual(data["ProgramArguments"], ["/usr/local/bin/myapp", "--minimized"])
                    self.assertTrue(data["RunAtLoad"])

                # 关闭自启
                res_remove = self.adapter.set_autostart(False)
                self.assertTrue(res_remove)
                self.assertFalse(os.path.exists(plist_path))


class WindowsAdapterUnitTests(unittest.TestCase):
    """验证 WindowsAdapter 行为及过滤。"""

    def setUp(self):
        self.adapter = WindowsAdapter()

    def test_hdr_state_returns_bool_without_error(self):
        state = self.adapter.get_hdr_state()
        self.assertIsInstance(state, bool)

    def test_filter_physical_interfaces_keeps_hardware(self):
        records = [
            SimpleNamespace(hardware_interface=True, filter_interface=False),
            SimpleNamespace(hardware_interface=False, filter_interface=False),
            SimpleNamespace(hardware_interface=True, filter_interface=True),
        ]
        res = self.adapter.filter_physical_interfaces(records)
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0].hardware_interface)

    def test_filter_physical_interfaces_name_filtering(self):
        names = ["Ethernet 1", "vEthernet (WSL)", "VirtualBox Host-Only", "Wi-Fi"]
        res = self.adapter.filter_physical_interfaces(names)
        self.assertEqual(res, ["Ethernet 1", "Wi-Fi"])


if __name__ == "__main__":
    unittest.main()
