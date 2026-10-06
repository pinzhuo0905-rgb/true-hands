"""核心循环。

这个循环与普通 Agent 的唯一区别，是**在「决策」和「执行」之间插了一道
策略网关**。模型说的话不算数，Guard 点头了才算数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..driver.base import Driver
from ..evidence.recorder import RunRecorder
from ..model.provider import ModelProvider
from ..policy.guard import Guard, PolicyViolation
from ..tasks.base import Task
from .verifier import GUIVerifier, Verifier

MAX_CONSECUTIVE_VIOLATIONS = 3


@dataclass
class RunResult:
    """一次运行的结论。"""

    success: bool
    steps: int
    summary: str
    policy_report: dict[str, Any]
    run_dir: str | None = None
    verified_by: str = ""

    def __str__(self) -> str:  # pragma: no cover - 仅用于打印
        flag = "✅ 成功" if self.success else "❌ 未通过"
        return (
            f"{flag} | 步数 {self.steps} | 违规 {self.policy_report.get('violation_count', 0)} 次\n"
            f"结论：{self.summary}\n证据目录：{self.run_dir or '(未记录)'}"
        )


class GUIOnlyHarness:
    """「只准操作界面」的 Agent 调度器。"""

    def __init__(
        self,
        driver: Driver,
        guard: Guard,
        model: ModelProvider,
        recorder: RunRecorder | None = None,
        verifier: Verifier | None = None,
        max_steps: int = 40,
        on_step: Callable[[int, str], None] | None = None,
    ) -> None:
        self.driver = driver
        self.guard = guard
        self.model = model
        self.recorder = recorder
        self.verifier = verifier or GUIVerifier(model)
        self.max_steps = max_steps
        self.on_step = on_step

    # -- 主流程 -------------------------------------------------------------
    def run(self, task: Task) -> RunResult:
        history: list[str] = []
        consecutive_violations = 0
        summary = "达到步数上限，任务未完成。"
        task_prompt = task.to_prompt()
        aborted = False

        for step in range(min(task.max_steps, self.max_steps)):
            before = self.driver.observe()

            # 上下文校验：焦点落在终端里时警告
            self.guard.check_context(before.window_title, step)

            decision = self.model.decide(task_prompt, before, history)

            if decision.done:
                summary = f"模型在第 {step} 步声明完成：{decision.thought}"
                break

            # ★ 关键一步：先过策略网关，再执行
            try:
                action = self.guard.check(decision.tool, decision.args, step)
            except PolicyViolation as exc:
                consecutive_violations += 1
                # 把拒绝理由回灌给模型，让它改正，而不是让它继续瞎撞
                history.append(
                    f"[第 {step} 步被拒绝] {decision.tool} —— {exc.record.reason}"
                )
                self._emit(step, f"⛔ 拒绝 {decision.tool}（{exc.record.rule}）")
                if consecutive_violations >= MAX_CONSECUTIVE_VIOLATIONS:
                    summary = (
                        f"连续 {consecutive_violations} 次试图绕过界面操作，已中止。"
                        f"最后一次：{exc.record.reason}"
                    )
                    aborted = True
                    break
                continue

            consecutive_violations = 0
            result = self.driver.act(action)
            after = result.observation or self.driver.observe()

            if self.recorder:
                self.recorder.record_step(
                    step=step, action=action, result=result, before=before, after=after
                )
            history.append(f"第 {step} 步：{action.tool} → {result.detail[:160]}")
            self._emit(step, f"▶ {action.tool} → {result.detail[:80]}")

        # -- 验收（同样走界面） -------------------------------------------
        # 若已因反复偷懒中止，则跳过验收——此时「没完成」是确定的事实，
        # 再跑验收只会覆盖掉真正的失败原因。
        if aborted:
            verified, reason = False, summary
        else:
            verified, reason = self.verifier.verify(task, self.driver, self.guard)
        run_dir = None
        if self.recorder:
            path = self.recorder.finish(
                task=task.name,
                success=verified,
                policy_report=self.guard.report(),
                summary=reason or summary,
            )
            run_dir = str(path.parent)

        return RunResult(
            success=verified,
            steps=len(history),
            summary=reason or summary,
            policy_report=self.guard.report(),
            run_dir=run_dir,
            verified_by=type(self.verifier).__name__,
        )

    def _emit(self, step: int, message: str) -> None:
        if self.on_step:
            self.on_step(step, message)
