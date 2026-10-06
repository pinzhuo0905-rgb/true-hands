"""Mock 驱动：不碰真实桌面，用于测试与 CI。

它记录下所有被请求的动作，方便断言「约束是否生效」——
比如测试「模型要求写文件时，Guard 有没有拦住」。
"""

from __future__ import annotations

from ..policy.guard import Action
from .base import ActionResult, Observation

# 与 Windows-MCP 对齐的工具集，便于测试白名单逻辑
DEFAULT_TOOLS = [
    "Screenshot", "Snapshot", "DisplayInventory",
    "Click", "Move", "Scroll", "MultiSelect",
    "Type", "Shortcut", "MultiEdit",
    "App", "Wait", "WaitFor", "Notification",
]


class MockDriver:
    """把动作记在内存里的假驱动。"""

    def __init__(self, tools: list[str] | None = None, window_title: str = "无标题 - 记事本") -> None:
        self._tools = list(tools or DEFAULT_TOOLS)
        self.window_title = window_title
        self.executed: list[Action] = []

    def list_tools(self) -> list[str]:
        return list(self._tools)

    def observe(self) -> Observation:
        return Observation(
            window_title=self.window_title,
            elements=[{"index": 0, "role": "editor", "name": "文本编辑区", "bounds": "0,0,800,600"}],
        )

    def act(self, action: Action) -> ActionResult:
        self.executed.append(action)
        return ActionResult(ok=True, detail=f"mock 执行了 {action.tool}", observation=self.observe())

    def close(self) -> None:
        return None
