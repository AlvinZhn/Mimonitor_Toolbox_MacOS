"""平台适配器包入口与单例工厂函数。"""

from __future__ import annotations

import sys
from typing import Optional

from .base import BasePlatformAdapter
from .macos import MacOSAdapter
from .windows import WindowsAdapter


class FallbackAdapter(BasePlatformAdapter):
    """通用降级平台适配器（用于 Linux 或未识别平台环境）。"""

    def get_hdr_state(self, window_handle=None) -> bool:
        return False

    def register_global_hotkey(self, hotkey_str, callback, **kwargs) -> bool:
        return False

    def unregister_all_hotkeys(self) -> None:
        pass

    def set_autostart(self, enable: bool, executable=None) -> bool:
        return False

    def get_autostart_path(self) -> Optional[str]:
        return None

    def filter_physical_interfaces(self, interfaces: list) -> list:
        return interfaces

    def enumerate_adapter_addresses(self) -> list:
        return []

    def get_bundled_adb_path(self) -> str:
        import shutil

        return shutil.which("adb") or "adb"

    def is_system_dark_theme(self) -> bool:
        return False


_adapter_instance: Optional[BasePlatformAdapter] = None


def get_platform_adapter() -> BasePlatformAdapter:
    """按当前运行时 sys.platform 返回平台适配器单例。"""
    global _adapter_instance
    if _adapter_instance is not None:
        return _adapter_instance

    if sys.platform == "win32":
        _adapter_instance = WindowsAdapter()
    elif sys.platform == "darwin":
        _adapter_instance = MacOSAdapter()
    else:
        _adapter_instance = FallbackAdapter()

    return _adapter_instance


def reset_platform_adapter() -> None:
    """重置单例实例（主要用于单元测试切换平台模拟）。"""
    global _adapter_instance
    _adapter_instance = None


__all__ = [
    "BasePlatformAdapter",
    "WindowsAdapter",
    "MacOSAdapter",
    "FallbackAdapter",
    "get_platform_adapter",
    "reset_platform_adapter",
]
