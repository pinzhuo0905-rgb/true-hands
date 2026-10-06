"""策略层：定义并执行「只准操作界面」的强制约束。"""

from .guard import Guard, PolicyViolation
from .rules import (
    ALLOWED_TOOLS,
    FORBIDDEN_EXECUTABLES,
    FORBIDDEN_TOOLS,
    SHELL_WINDOW_HINTS,
    is_tool_allowed,
)

__all__ = [
    "Guard",
    "PolicyViolation",
    "ALLOWED_TOOLS",
    "FORBIDDEN_TOOLS",
    "FORBIDDEN_EXECUTABLES",
    "SHELL_WINDOW_HINTS",
    "is_tool_allowed",
]
