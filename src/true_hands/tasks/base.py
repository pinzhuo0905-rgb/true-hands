"""任务抽象。

一个任务 = 目标描述 + 验收方式。

注意 ``verify_prompt``：**验收也必须走界面**。不能写「检查桌面文件是否存在」，
而要写「在资源管理器里打开桌面，看一眼有没有这个文件，并打开它确认内容」。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    """一个 GUI 任务。"""

    name: str
    goal: str
    """给模型看的目标描述。"""

    app_hint: str = ""
    """建议使用的软件（如 "Microsoft Word" / "记事本"）。"""

    verify_prompt: str = ""
    """验收指令。同样必须是界面操作。"""

    success_criteria: str = ""
    """判定成功的标准，供验收时对照。"""

    max_steps: int = 40
    metadata: dict = field(default_factory=dict)

    def to_prompt(self) -> str:
        lines = [f"任务：{self.goal}"]
        if self.app_hint:
            lines.append(f"建议使用软件：{self.app_hint}")
        if self.success_criteria:
            lines.append(f"成功标准：{self.success_criteria}")
        return "\n".join(lines)
