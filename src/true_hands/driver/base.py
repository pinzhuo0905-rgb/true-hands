"""驱动抽象层。

驱动只负责「执行一个原子动作」，**不做任何决策、不做任何策略判断**——
策略判断在 :mod:`true_hands.policy` 里完成，职责严格分离。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..policy.guard import Action


@dataclass
class Observation:
    """一次「看屏幕」的结果。"""

    window_title: str = ""
    screenshot_path: str | None = None
    elements: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_prompt(self) -> str:
        """转成给模型看的文本描述（截图路径另行以图片形式传入）。"""
        lines = [f"当前窗口：{self.window_title or '(未知)'}"]
        if self.elements:
            lines.append(f"可见元素 {len(self.elements)} 个：")
            for el in self.elements[:60]:
                lines.append(
                    f"  - [{el.get('index', '?')}] {el.get('role', '')} "
                    f"\"{el.get('name', '')}\" @{el.get('bounds', '')}"
                )
        return "\n".join(lines)


@dataclass
class ActionResult:
    """一次动作的执行结果。"""

    ok: bool
    detail: str = ""
    observation: Observation | None = None


@runtime_checkable
class Driver(Protocol):
    """桌面驱动协议。

    任何实现都可以接入——只要它能「看屏幕」和「动手」。
    内置实现见 :mod:`true_hands.driver.mcp_client` 与
    :mod:`true_hands.driver.mock`。
    """

    def list_tools(self) -> list[str]:
        """返回该驱动提供的全部工具名（用于与策略白名单做交叉检查）。"""
        ...

    def observe(self) -> Observation:
        """看一次屏幕。"""
        ...

    def act(self, action: Action) -> ActionResult:
        """执行一个动作。调用方必须保证该动作已通过 :class:`Guard` 校验。"""
        ...

    def close(self) -> None:
        """释放资源（关闭子进程等）。"""
        ...
