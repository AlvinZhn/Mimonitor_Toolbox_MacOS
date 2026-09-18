"""Windows 平台适配器实现。"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Optional

from ..windows import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    dispatch_power_broadcast,
    get_autostart_path,
    get_executable_path,
    install_autostart,
    query_windows_hdr_enabled,
    remove_autostart,
    user32,
)
from .base import BasePlatformAdapter


class WindowsAdapter(BasePlatformAdapter):
    """Windows 原生能力平台适配器。"""

    def __init__(self) -> None:
        self._hotkey_registry: dict[int, tuple[Any, Callable[[], None]]] = {}
        self._next_hotkey_id = 1

    def get_hdr_state(self, window_handle: Any = None) -> bool:
        """获取 Windows 系统 HDR 状态。"""
        res = query_windows_hdr_enabled(window_handle)
        return bool(res)

    def register_global_hotkey(
        self,
        hotkey_str: str,
        callback: Callable[[], None],
        **kwargs: Any,
    ) -> bool:
        """注册 Windows 全局热键。"""
        if sys.platform != "win32" or not user32:
            return False

        hwnd = kwargs.get("hwnd", 0)
        mod_val = kwargs.get("mod_val")
        vk_val = kwargs.get("vk_val")

        # 若未直接传入 mod_val 与 vk_val，支持解析类似 "Ctrl + Alt + F1"
        if mod_val is None or vk_val is None:
            mod_val, vk_val = self._parse_hotkey_str(hotkey_str)

        if vk_val == 0:
            return False

        hotkey_id = kwargs.get("hotkey_id", self._next_hotkey_id)
        res = user32.RegisterHotKey(int(hwnd), int(hotkey_id), int(mod_val), int(vk_val))
        if res:
            self._hotkey_registry[hotkey_id] = (hwnd, callback)
            if hotkey_id == self._next_hotkey_id:
                self._next_hotkey_id += 1
            return True
        return False

    def unregister_all_hotkeys(self) -> None:
        """注销所有由该适配器登记的全局热键。"""
        if sys.platform != "win32" or not user32:
            self._hotkey_registry.clear()
            return

        for hid, (hwnd, _) in list(self._hotkey_registry.items()):
            try:
                user32.UnregisterHotKey(int(hwnd), int(hid))
            except Exception:
                pass
        self._hotkey_registry.clear()

    def set_autostart(self, enable: bool, executable: Optional[str] = None) -> bool:
        """设置或移除 Windows 开机启动。"""
        if enable:
            return install_autostart(executable)
        return remove_autostart()

    def get_autostart_path(self) -> Optional[str]:
        """获取 Windows 开机启动批处理文件路径。"""
        return get_autostart_path()

    def filter_physical_interfaces(self, interfaces: list) -> list:
        """根据网卡属性/名称过滤 Windows 物理网卡。"""
        filtered = []
        for iface in interfaces:
            # 支持 RawAdapterAddress 对象
            if hasattr(iface, "hardware_interface"):
                if getattr(iface, "hardware_interface", False) and not getattr(iface, "filter_interface", False):
                    filtered.append(iface)
                continue
            # 支持字典
            if isinstance(iface, dict):
                if iface.get("hardware_interface", True) and not iface.get("filter_interface", False):
                    filtered.append(iface)
                continue
            # 支持名称过滤
            name = str(iface).lower()
            if not any(virt in name for virt in ("vethernet", "virtual", "pseudo", "loopback", "tap", "wsl")):
                filtered.append(iface)
        return filtered

    def enumerate_adapter_addresses(self) -> list:
        """调用 Windows IP Helper API 枚举网卡。"""
        from ..network_scan import enumerate_windows_adapter_addresses

        return enumerate_windows_adapter_addresses()

    def get_bundled_adb_path(self) -> str:
        """获取 Windows 环境下的 adb 路径。"""
        from ..core import bundled_resource_path, get_app_data_dir, is_frozen_build

        # 优先在打包态解压运行时
        if is_frozen_build():
            try:
                import shutil

                runtime_dir = os.path.join(get_app_data_dir(), "runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                for filename in ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"):
                    src = bundled_resource_path("assets", "runtime", filename)
                    if not src or not os.path.exists(src):
                        continue
                    dst = os.path.join(runtime_dir, filename)
                    try:
                        same_file = os.path.abspath(src).lower() == os.path.abspath(dst).lower()
                    except Exception:
                        same_file = False
                    if same_file:
                        continue
                    should_copy = not os.path.exists(dst)
                    if not should_copy:
                        try:
                            should_copy = os.path.getsize(src) != os.path.getsize(dst) or int(os.path.getmtime(src)) > int(os.path.getmtime(dst))
                        except Exception:
                            should_copy = True
                    if should_copy:
                        shutil.copy2(src, dst)
                persistent_adb = os.path.join(runtime_dir, "adb.exe")
                if os.path.exists(persistent_adb):
                    return persistent_adb
            except Exception:
                pass

        p = bundled_resource_path("assets", "runtime", "adb.exe")
        if p and os.path.exists(p):
            return p
        return "adb.exe"

    @staticmethod
    def _parse_hotkey_str(hotkey_str: str) -> tuple[int, int]:
        """简易解析修饰键与按键。"""
        mod_val = 0
        vk_val = 0
        parts = [p.strip() for p in hotkey_str.split("+") if p.strip()]
        for part in parts[:-1]:
            low = part.lower()
            if "ctrl" in low:
                mod_val |= MOD_CONTROL
            elif "alt" in low:
                mod_val |= MOD_ALT
            elif "shift" in low:
                mod_val |= MOD_SHIFT
            elif "win" in low:
                mod_val |= MOD_WIN

        if parts:
            key = parts[-1]
            if len(key) == 1:
                vk_val = ord(key.upper())
            elif key.startswith("F") and key[1:].isdigit():
                vk_val = 0x6F + int(key[1:])
        return mod_val, vk_val

    def is_system_dark_theme(self) -> bool:
        """探测 Windows 当前是否处于深色主题模式。"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
        except Exception:
            return False
