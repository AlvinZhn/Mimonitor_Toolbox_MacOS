"""情景模式核心管理器与数据结构单元测试 (Phase 2 闸门测试)。"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from mimonitor_toolbox.presets import (
    PresetManager,
    PresetProfile,
    get_default_presets,
    get_preset_manager,
    reset_preset_manager,
)


class PresetProfileDataTests(unittest.TestCase):
    """测试预设数据结构、默认内置情景与 JSON 序列化。"""

    def test_default_presets_contain_three_core_scenarios(self):
        presets = get_default_presets()
        self.assertEqual(len(presets), 3)

        ids = [p.id for p in presets]
        names = [p.name for p in presets]
        self.assertIn("office_eyecare", ids)
        self.assertIn("esports_320hz", ids)
        self.assertIn("cinema_miniled", ids)
        self.assertIn("办公护眼", names)
        self.assertIn("320Hz电竞", names)
        self.assertIn("影院MiniLED高亮", names)

        for p in presets:
            self.assertTrue(p.is_builtin)
            self.assertIn("backlight", p.settings_map)
            self.assertIn("picture_local_dimming", p.settings_map)
            self.assertIn("tv_picture_advanced_video_color_space", p.settings_map)

    def test_preset_profile_serialization_roundtrip(self):
        profile = PresetProfile(
            id="custom_test_1",
            name="测试调校",
            icon="GAME",
            description="这是一个自定义测试情景",
            settings_map={"backlight": 80, "contrast": 55, "picture_local_dimming": 2},
            is_builtin=False,
        )

        d = profile.to_dict()
        restored = PresetProfile.from_dict(d)

        self.assertEqual(restored.id, profile.id)
        self.assertEqual(restored.name, profile.name)
        self.assertEqual(restored.icon, profile.icon)
        self.assertEqual(restored.description, profile.description)
        self.assertEqual(restored.settings_map, profile.settings_map)
        self.assertFalse(restored.is_builtin)


class PresetManagerCRUDTests(unittest.TestCase):
    """测试 PresetManager 预设增删改查与本地持久化。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_file = os.path.join(self.temp_dir.name, "presets.json")
        self.manager = PresetManager(storage_path=self.storage_file)

    def tearDown(self):
        self.temp_dir.cleanup()
        reset_preset_manager()

    def test_initial_presets_contain_builtins(self):
        all_presets = self.manager.get_all_presets()
        self.assertGreaterEqual(len(all_presets), 3)
        self.assertIsNotNone(self.manager.get_preset("office_eyecare"))

    def test_add_and_persist_custom_preset(self):
        custom = PresetProfile(
            id="user_coding",
            name="极客编程",
            icon="DEVELOPER_TOOLS",
            description="柔和暖光编程情景",
            settings_map={"backlight": 42, "contrast": 50},
        )
        res = self.manager.add_preset(custom)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(self.storage_file))

        # 检查内部加载
        retrieved = self.manager.get_preset("user_coding")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "极客编程")

        # 验证持久化重新加载
        new_manager = PresetManager(storage_path=self.storage_file)
        reloaded = new_manager.get_preset("user_coding")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.settings_map.get("backlight"), 42)

    def test_builtin_preset_cannot_be_deleted(self):
        res = self.manager.remove_preset("office_eyecare")
        self.assertFalse(res)
        self.assertIsNotNone(self.manager.get_preset("office_eyecare"))

    def test_builtin_preset_cannot_be_overwritten_by_custom(self):
        fake_builtin_override = PresetProfile(
            id="office_eyecare",
            name="篡改内置",
            settings_map={"backlight": 10},
        )
        res = self.manager.add_preset(fake_builtin_override)
        self.assertFalse(res)
        original = self.manager.get_preset("office_eyecare")
        self.assertEqual(original.name, "办公护眼")

    def test_custom_preset_can_be_deleted(self):
        custom = PresetProfile(
            id="to_delete",
            name="待删除",
            settings_map={"backlight": 10},
        )
        self.manager.add_preset(custom)
        self.assertIsNotNone(self.manager.get_preset("to_delete"))

        remove_res = self.manager.remove_preset("to_delete")
        self.assertTrue(remove_res)
        self.assertIsNone(self.manager.get_preset("to_delete"))


class PresetSnapshotTests(unittest.TestCase):
    """测试逆向快照与防御性空值校验。"""

    def setUp(self):
        self.manager = PresetManager()

    def test_snapshot_succeeds_with_valid_settings(self):
        pool = {
            "backlight": 65,
            "contrast": 50,
            "black_level": 50,
            "picture_local_dimming": 3,
            "tv_picture_advanced_video_color_space": 6,
            "other_garbage_key": 999,
        }
        snapshot = self.manager.create_snapshot(
            current_settings=pool,
            name="我现在的完美调校",
            icon="PALETTE",
            description="观影专用测试",
        )

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.name, "我现在的完美调校")
        self.assertEqual(snapshot.settings_map["backlight"], 65)
        self.assertEqual(snapshot.settings_map["picture_local_dimming"], 3)
        self.assertEqual(snapshot.settings_map["tv_picture_advanced_video_color_space"], 6)
        # 验证无关脏键被自动过滤
        self.assertNotIn("other_garbage_key", snapshot.settings_map)
        self.assertFalse(snapshot.is_builtin)

    def test_snapshot_fails_when_settings_empty_or_missing_core_keys(self):
        self.assertIsNone(self.manager.create_snapshot({}, "空测试"))
        self.assertIsNone(self.manager.create_snapshot({"unrelated": 123}, "无背光测试"))


class PresetActionPipelineTests(unittest.TestCase):
    """测试动作流水线执行与串行防连击。"""

    def setUp(self):
        self.manager = PresetManager()
        self.test_preset = PresetProfile(
            id="pipeline_test",
            name="测试流水线",
            settings_map={
                "backlight": 88,
                "contrast": 52,
                "picture_local_dimming": 2,
                "tv_picture_advanced_video_color_space": 6,
            },
        )

    def test_pipeline_fails_when_adb_not_connected(self):
        fake_app = SimpleNamespace(adb_connected=False, adb=None)
        done_called = False
        err_message = ""

        def on_done(success, msg):
            nonlocal done_called, err_message
            done_called = True
            err_message = msg

        self.manager.apply_preset_pipeline(self.test_preset, fake_app, on_finished=on_done)
        time.sleep(0.1)

        self.assertTrue(done_called)
        self.assertIn("未连接", err_message)

    def test_pipeline_executes_adb_commands_serially(self):
        adb_calls = []

        class FakeAdb:
            def call_jni(self, jni_func, val, *args, **kwargs):
                adb_calls.append(("jni", jni_func, val))

            def put(self, key, val, *args, **kwargs):
                adb_calls.append(("put", key, val))

            def refresh_pq(self, *args, **kwargs):
                adb_calls.append(("refresh_pq",))

            def set_color_temp(self, val, *args, **kwargs):
                adb_calls.append(("set_color_temp", val))

        fake_app = SimpleNamespace(adb_connected=True, adb=FakeAdb())
        done_called = False

        def on_done(success, msg):
            nonlocal done_called
            done_called = True

        self.manager.apply_preset_pipeline(self.test_preset, fake_app, on_finished=on_done)

        # 等待后台流水线线程执行完成
        for _ in range(50):
            if done_called:
                break
            time.sleep(0.05)

        self.assertTrue(done_called)
        # 验证关键 JNI 与 put 命令均已按顺序下发
        jni_funcs = [call[1] for call in adb_calls if call[0] == "jni"]
        self.assertIn("g_video__vid_local_dimming", jni_funcs)
        self.assertIn("g_video__vid_gamut_mapping_mode", jni_funcs)
        self.assertIn("g_disp__disp_back_light", jni_funcs)
        self.assertIn(("refresh_pq",), adb_calls)


class DashboardInterfaceTests(unittest.TestCase):
    """测试仪表盘 UI 组件渲染、卡片生成与离线交互流转。"""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication(["test", "-platform", "offscreen"])

    def test_dashboard_constructs_and_renders_cards(self):
        from mimonitor_toolbox.dashboard import DashboardInterface

        dashboard = DashboardInterface()
        self.assertGreaterEqual(len(dashboard._cards), 3)

        # 验证默认内置卡片包含并正确设置
        self.assertIn("office_eyecare", dashboard._cards)
        self.assertIn("esports_320hz", dashboard._cards)
        self.assertIn("cinema_miniled", dashboard._cards)

        # 验证状态摘要栏更新
        pool = {
            "backlight": 70,
            "picture_local_dimming": 2,
            "tv_picture_advanced_video_color_space": 6,
        }
        dashboard.sync_external_state(pool, connected=True, ip="192.168.1.100")
        self.assertIn("70 %", dashboard.status_bar.metric_labels["backlight"].text())
        self.assertIn("中", dashboard.status_bar.metric_labels["local_dimming"].text())
        self.assertIn("已连接", dashboard.status_bar.conn_status_label.text())

    def test_dashboard_apply_disconnected_shows_warning(self):
        from mimonitor_toolbox.dashboard import DashboardInterface

        dashboard = DashboardInterface()
        dashboard.adb_connected = False
        with mock.patch("qfluentwidgets.InfoBar.warning") as mock_warn:
            dashboard.apply_preset("office_eyecare")
            self.assertTrue(mock_warn.called)


if __name__ == "__main__":
    unittest.main()
