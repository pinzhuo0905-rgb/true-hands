"""验收层：证明任务真的完成了——而且是用界面证明的。

这是本项目区别于普通 Agent 的第二道防线。很多 Agent 会「自己说完成了」，
但这里的验收必须**再看一次屏幕**。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..driver.base import Driver
from ..model.provider import ModelProvider
from ..policy.guard import Guard, PolicyViolation
from ..tasks.base import Task


@runtime_checkable
class Verifier(Protocol):
    def verify(self, task: Task, driver: Driver, guard: Guard) -> tuple[bool, str]:
        """返回 (是否通过, 说明)。"""
        ...


class GUIVerifier:
    """界面验收器。

    让模型按 ``task.verify_prompt`` 再走几步**界面操作**（打开资源管理器、
    双击文件、看一眼），再下结论。

    它刻意**不提供任何读文件的途径**——所以「验收通过」这件事本身
    也是界面操作的产物，无法伪造。
    """

    def __init__(self, model: ModelProvider, max_steps: int = 6) -> None:
        self.model = model
        self.max_steps = max_steps

    def verify(self, task: Task, driver: Driver, guard: Guard) -> tuple[bool, str]:
        if not task.verify_prompt:
            return False, "任务未提供验收方式（verify_prompt 为空），无法确认结果。"

        history: list[str] = []
        last_thought = ""
        for step in range(self.max_steps):
            obs = driver.observe()
            decision = self.model.decide(task.verify_prompt, obs, history)
            last_thought = decision.thought or last_thought

            if decision.done:
                return True, f"界面验收通过：{last_thought}"

            try:
                action = guard.check(decision.tool, decision.args, step)
            except PolicyViolation as exc:
                history.append(f"[验收步骤被拒绝] {exc.record.reason}")
                continue

            result = driver.act(action)
            history.append(f"验收步骤 {step}：{action.tool} → {result.detail[:160]}")

        return False, f"验收未能在 {self.max_steps} 步内确认完成。最后判断：{last_thought}"
