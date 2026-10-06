"""执行层：把校验过的动作变成真实的桌面操作。"""

from .base import ActionResult, Driver, Observation
from .mock import MockDriver
from .native import create_native_driver, native_available

__all__ = [
    "Driver",
    "Observation",
    "ActionResult",
    "MockDriver",
    "create_native_driver",
    "native_available",
]
