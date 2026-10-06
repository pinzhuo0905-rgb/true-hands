"""原生驱动工厂：按平台挑一个「装上就能用」的驱动。

目前实现了 Windows（ctypes 直调 Win32 API）。其他平台请用 MCP 驱动：

* macOS   → agent-desktop
* Linux   → computer-use-linux
"""

from __future__ import annotations

import os
from typing import Any

from .base import Driver


def create_native_driver(**kwargs: Any) -> Driver:
    """创建当前平台的原生驱动。"""
    if os.name == "nt":
        from .native_win32 import NativeDesktopDriver

        return NativeDesktopDriver(**kwargs)  # type: ignore[return-value]
    raise RuntimeError(
        "本平台暂未内置原生驱动。请改用 MCP 驱动：\n"
        "  macOS → agent-desktop\n"
        "  Linux → computer-use-linux\n"
        "例如：--driver mcp --driver-command computer-use-linux"
    )


def native_available() -> bool:
    """当前平台是否有内置原生驱动。"""
    return os.name == "nt"


__all__ = ["create_native_driver", "native_available"]
