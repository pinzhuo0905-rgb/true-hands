"""执行层：把校验过的动作变成真实的桌面操作。"""

from .base import ActionResult, Driver, Observation

__all__ = ["Driver", "Observation", "ActionResult"]
