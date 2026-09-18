"""情景模式（Presets）模块入口。"""

from .manager import (
    PresetManager,
    PresetProfile,
    get_default_presets,
    get_preset_manager,
    reset_preset_manager,
)

__all__ = [
    "PresetProfile",
    "PresetManager",
    "get_default_presets",
    "get_preset_manager",
    "reset_preset_manager",
]
