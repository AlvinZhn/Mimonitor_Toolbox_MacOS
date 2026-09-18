"""跨平台适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class BasePlatformAdapter(ABC):
    """定义不同操作系统底层能力接口的抽象基类。"""

    @abstractmethod
    def get_hdr_state(self, window_handle: Any = None) -> bool:
        """获取系统当前 HDR 开启状态。

        :param window_handle: 可选窗口句柄，用于精准匹配对应显示器。
        :return: True 为开启，False 为关闭或不支持。
        """
        pass

    @abstractmethod
    def register_global_hotkey(
        self,
        hotkey_str: str,
        callback: Callable[[], None],
        **kwargs: Any,
    ) -> bool:
        """注册全局快捷键。

        :param hotkey_str: 快捷键文本描述，如 "Ctrl + Alt + F1"。
        :param callback: 触发回调函数。
        :return: 注册成功返回 True，失败或降级返回 False。
        """
        pass

    @abstractmethod
    def unregister_all_hotkeys(self) -> None:
        """注销所有已注册的快捷键。"""
        pass

    @abstractmethod
    def set_autostart(self, enable: bool, executable: Optional[str] = None) -> bool:
        """配置或取消开机自启动。

        :param enable: True 为开启自启，False 为取消自启。
        :param executable: 可选指定的可执行文件路径。
        :return: 操作成功返回 True，失败返回 False。
        """
        pass

    @abstractmethod
    def get_autostart_path(self) -> Optional[str]:
        """获取开机自启动配置文件或链接的存储路径。"""
        pass

    @abstractmethod
    def filter_physical_interfaces(self, interfaces: list) -> list:
        """过滤虚拟网卡，仅保留物理局域网网卡。

        :param interfaces: 网卡名称列表，或带有 interface_name / name 属性/键的对象列表。
        :return: 过滤后的物理网卡列表。
        """
        pass

    @abstractmethod
    def enumerate_adapter_addresses(self) -> list:
        """枚举当前系统适合探测的物理 IPv4 网卡地址记录列表。

        :return: RawAdapterAddress 对象列表。
        """
        pass

    @abstractmethod
    def get_bundled_adb_path(self) -> str:
        """获取适配当前 OS 的 ADB 执行路径。

        :return: ADB 可执行文件绝对路径或 "adb"。
        """
        pass
