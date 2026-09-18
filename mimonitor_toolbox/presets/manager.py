"""情景模式（Presets）核心数据结构、持久化与动作流水线管理器。"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..core import get_app_data_dir


@dataclass
class PresetProfile:
    """单个情景模式的数据配置结构。"""

    id: str
    name: str
    icon: str = "PALETTE"
    description: str = ""
    settings_map: Dict[str, Any] = field(default_factory=dict)
    is_builtin: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PresetProfile:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "未命名情景")),
            icon=str(data.get("icon", "PALETTE")),
            description=str(data.get("description", "")),
            settings_map=dict(data.get("settings_map", {})),
            is_builtin=bool(data.get("is_builtin", False)),
            created_at=float(data.get("created_at", time.time())),
        )


def get_default_presets() -> List[PresetProfile]:
    """获取 3 个开箱即用的默认内置情景模式。"""
    return [
        PresetProfile(
            id="office_eyecare",
            name="办公护眼",
            icon="VIEW",
            description="低蓝光护眼原色调校，柔和背光减少视疲劳，适合长时间文字与代码编写。",
            settings_map={
                "backlight": 35,
                "contrast": 50,
                "black_level": 50,
                "saturation": 50,
                "picture_local_dimming": 0,  # 关
                "picture_color_temperature": 8,  # 原色
                "tv_picture_advanced_video_color_space": 3,  # sRGB
                "picture_response_time": 1,  # 普通
                "picture_dynamic_definition": 0,  # 关
                "mt_colorful_led_mode": 0,  # 关
            },
            is_builtin=True,
        ),
        PresetProfile(
            id="esports_320hz",
            name="320Hz电竞",
            icon="GAME",
            description="高速灰阶响应与高刷新竞技调校，开启快速控光与电竞氛围灯，制霸对战。",
            settings_map={
                "backlight": 75,
                "contrast": 55,
                "black_level": 50,
                "saturation": 55,
                "picture_local_dimming": 2,  # 中
                "picture_color_temperature": 1,  # 标准
                "tv_picture_advanced_video_color_space": 6,  # DCI-P3
                "picture_response_time": 3,  # 高速
                "picture_dynamic_definition": 1,  # 低
                "mt_colorful_led_mode": 1,  # 常亮
                "game_refresh_rate": 1,  # 320Hz竞技模式
            },
            is_builtin=True,
        ),
        PresetProfile(
            id="cinema_miniled",
            name="影院MiniLED高亮",
            icon="VIDEO",
            description="高精密控光全开，100%峰值背光与广色域映射，沉浸式高动态HDR观影。",
            settings_map={
                "backlight": 100,
                "contrast": 60,
                "black_level": 50,
                "saturation": 52,
                "picture_local_dimming": 3,  # 高
                "picture_color_temperature": 2,  # 暖色
                "tv_picture_advanced_video_color_space": 6,  # DCI-P3
                "picture_response_time": 2,  # 快速
                "picture_dynamic_definition": 0,  # 关
                "mt_colorful_led_mode": 3,  # 炫彩流光
            },
            is_builtin=True,
        ),
    ]


class PresetManager:
    """管理预设加载、持久化、逆向快照与流水线执行。"""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path:
            self.storage_path = storage_path
        else:
            # 优先保存于 ~/.mimonitor_toolbox/presets.json
            home_dir = os.path.expanduser("~/.mimonitor_toolbox")
            self.storage_path = os.path.join(home_dir, "presets.json")

        self._lock = threading.RLock()
        self._presets: List[PresetProfile] = []
        self._active_preset_id: Optional[str] = None
        self._is_applying = False
        self.load_presets()

    @property
    def is_applying(self) -> bool:
        return self._is_applying

    @property
    def active_preset_id(self) -> Optional[str]:
        return self._active_preset_id

    def set_active_preset_id(self, preset_id: Optional[str]) -> None:
        self._active_preset_id = preset_id

    def load_presets(self) -> List[PresetProfile]:
        """从文件加载预设列表，合并内置预设。"""
        with self._lock:
            builtin_map = {p.id: p for p in get_default_presets()}
            custom_presets: List[PresetProfile] = []

            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                profile = PresetProfile.from_dict(item)
                                if profile.id not in builtin_map:
                                    profile.is_builtin = False
                                    custom_presets.append(profile)
                except Exception:
                    pass

            self._presets = list(builtin_map.values()) + custom_presets
            return list(self._presets)

    def save_presets(self) -> bool:
        """持久化存储所有自定义预设。"""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                custom_data = [p.to_dict() for p in self._presets if not p.is_builtin]
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(custom_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception:
                return False

    def get_all_presets(self) -> List[PresetProfile]:
        with self._lock:
            return list(self._presets)

    def get_preset(self, preset_id: str) -> Optional[PresetProfile]:
        with self._lock:
            for p in self._presets:
                if p.id == preset_id:
                    return p
            return None

    def add_preset(self, preset: PresetProfile) -> bool:
        """新增或更新情景模式并持久化。"""
        with self._lock:
            # 内置预设禁止同名覆盖或被标记为内置
            existing_idx = next(
                (i for i, p in enumerate(self._presets) if p.id == preset.id),
                None,
            )
            if existing_idx is not None:
                if self._presets[existing_idx].is_builtin:
                    return False
                self._presets[existing_idx] = preset
            else:
                self._presets.append(preset)
            return self.save_presets()

    def remove_preset(self, preset_id: str) -> bool:
        """删除指定的自定义情景模式（内置预设不可删除）。"""
        with self._lock:
            target = self.get_preset(preset_id)
            if not target or target.is_builtin:
                return False
            self._presets = [p for p in self._presets if p.id != preset_id]
            if self._active_preset_id == preset_id:
                self._active_preset_id = None
            return self.save_presets()

    def create_snapshot(
        self,
        current_settings: dict,
        name: str,
        icon: str = "PALETTE",
        description: str = "",
    ) -> Optional[PresetProfile]:
        """逆向快照功能：根据当前显示器生效参数组装为新预设对象。

        具备空值与不完整防护：当参数字典为空或缺少核心背光参数时返回 None。
        """
        if not current_settings or not isinstance(current_settings, dict):
            return None

        # 检查是否包含核心基础参数
        essential_keys = ("backlight", "contrast", "picture_local_dimming")
        found = any(k in current_settings for k in essential_keys)
        if not found:
            return None

        # 过滤并提取已知的显示器核心调校参数
        recognized_keys = (
            "backlight",
            "contrast",
            "black_level",
            "saturation",
            "hue",
            "sharpness",
            "picture_local_dimming",
            "picture_color_temperature",
            "tv_picture_advanced_video_color_space",
            "picture_response_time",
            "picture_dynamic_definition",
            "mt_colorful_led_mode",
            "game_refresh_rate",
        )

        extracted = {}
        for k in recognized_keys:
            if k in current_settings and current_settings[k] is not None:
                extracted[k] = current_settings[k]

        if not extracted:
            return None

        preset_id = f"custom_{int(time.time() * 1000)}"
        return PresetProfile(
            id=preset_id,
            name=name.strip() or "自定义情景",
            icon=icon,
            description=description.strip() or "用户自定义显示器状态快照",
            settings_map=extracted,
            is_builtin=False,
        )

    def execute_preset_pipeline(
        self,
        preset: PresetProfile,
        app: Any,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ) -> tuple[bool, str]:
        """同步执行情景参数下发动作流水线，严格保证串行与原子性，返回 (success, message)。"""
        with self._lock:
            if self._is_applying:
                return False, "正在应用其他情景，请稍候..."
            self._is_applying = True

        try:
            if not getattr(app, "adb_connected", False) or not getattr(app, "adb", None):
                raise RuntimeError("尚未连接显示器，请先在主页完成 ADB 连接")

            adb = app.adb
            settings = preset.settings_map
            total_steps = len(settings) + 1
            current_step = 0

            def step_notify(desc: str):
                nonlocal current_step
                current_step += 1
                percent = int((current_step / total_steps) * 100)
                if on_progress:
                    on_progress(desc, percent)

            # 1. 控光档位 (JNI g_video__vid_local_dimming)
            if "picture_local_dimming" in settings:
                val = int(settings["picture_local_dimming"])
                step_notify("设置精密控光")
                try:
                    adb.call_jni(
                        "g_video__vid_local_dimming",
                        val,
                        "tv_picture_video_local_dimming",
                        check=True,
                    )
                    adb.put("picture_local_dimming", str(val), check=False)
                except Exception:
                    pass

            # 2. 色域映射 (JNI g_video__vid_gamut_mapping_mode)
            if "tv_picture_advanced_video_color_space" in settings:
                val = int(settings["tv_picture_advanced_video_color_space"])
                step_notify("切换色彩空间与色域")
                try:
                    adb.call_jni("g_video__vid_gamut_mapping_mode", val, check=True)
                    adb.put("tv_picture_advanced_video_color_space", str(val), check=False)
                except Exception:
                    pass

            # 3. 色温预设
            if "picture_color_temperature" in settings:
                val = int(settings["picture_color_temperature"])
                step_notify("调整色温模式")
                try:
                    adb.set_color_temp(val, check=True)
                except Exception:
                    pass

            # 4. 画面预设模式 (picture_mode)
            if "picture_mode" in settings:
                val = int(settings["picture_mode"])
                step_notify("切换画面显示模式")
                try:
                    adb.put("picture_mode", str(val), check=True)
                    adb.put("picture_preset_scenario", str(val), check=False)
                except Exception:
                    pass

            # 5. 对比度
            if "contrast" in settings:
                val = int(settings["contrast"])
                step_notify("调整画面对比度")
                try:
                    adb.put("picture_contrast", str(val), check=False)
                except Exception:
                    pass

            # 6. 黑色级别
            if "black_level" in settings:
                val = int(settings["black_level"])
                step_notify("调整黑色级别")
                try:
                    adb.put("picture_brightness", str(val), check=False)
                except Exception:
                    pass

            # 7. 饱和度
            if "saturation" in settings:
                val = int(settings["saturation"])
                step_notify("调整色彩饱和度")
                try:
                    adb.put("picture_saturation", str(val), check=False)
                except Exception:
                    pass

            # 8. 锐度
            if "sharpness" in settings:
                val = int(settings["sharpness"])
                step_notify("调整画面锐度")
                try:
                    adb.put("picture_sharpness", str(val), check=False)
                except Exception:
                    pass

            # 9. 背光亮度 (最后下发保证视觉舒适)
            if "backlight" in settings:
                val = int(settings["backlight"])
                step_notify("调整背光亮度")
                try:
                    adb.call_jni("g_disp__disp_back_light", val, check=True)
                    adb.put("picture_backlight", str(val), check=False)
                    adb.put("xiaomi_picture_backlight", str(val), check=False)
                except Exception:
                    pass

            # 10. 刷新 PQ 与全局状态回读同步
            step_notify("刷新画质引擎与同步状态")
            try:
                adb.refresh_pq(check=True)
            except Exception:
                pass

            self._active_preset_id = preset.id
            return True, f"情景【{preset.name}】已成功应用"
        except Exception as exc:
            return False, str(exc)
        finally:
            with self._lock:
                self._is_applying = False

    def apply_preset_pipeline(
        self,
        preset: PresetProfile,
        app: Any,
        on_progress: Optional[Callable[[str, int], None]] = None,
        on_finished: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """动作流水线执行器：异步下发情景参数。"""
        def _worker():
            success, msg = self.execute_preset_pipeline(preset, app, on_progress)
            if on_finished:
                on_finished(success, msg)

        threading.Thread(target=_worker, daemon=True).start()


_manager_instance: Optional[PresetManager] = None


def get_preset_manager() -> PresetManager:
    """获取 PresetManager 全局单例。"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PresetManager()
    return _manager_instance


def reset_preset_manager() -> None:
    """重置单例（主要用于单元测试）。"""
    global _manager_instance
    _manager_instance = None
