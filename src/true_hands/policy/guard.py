"""策略网关：所有动作在执行前必须过这一关。

这是「强制约束」的落地点。Agent 提出的每一个动作都要经过 :class:`Guard`
校验；不通过的动作**不会被执行**，而是被记入违规日志。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .rules import (
    ALLOWED_TOOLS,
    FORBIDDEN_TOOLS,
    is_executable_forbidden,
    is_tool_allowed,
    looks_like_shell_window,
)

GuardMode = Literal["enforce", "audit"]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Action:
    """一个待执行的动作。"""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志
        return f"{self.tool}({self.args})"


@dataclass(frozen=True)
class ViolationRecord:
    """一次违规记录。"""

    step: int | None
    tool: str
    args: dict[str, Any]
    rule: str
    reason: str


class PolicyViolation(Exception):
    """动作违反了「只准操作界面」的约束。"""

    def __init__(self, record: ViolationRecord) -> None:
        self.record = record
        super().__init__(f"[{record.rule}] {record.tool}: {record.reason}")


# ---------------------------------------------------------------------------
# 网关
# ---------------------------------------------------------------------------
class Guard:
    """策略网关。

    Parameters
    ----------
    mode:
        ``"enforce"`` —— 违规直接抛异常，动作不会执行（默认，也是本项目的意义所在）。
        ``"audit"``   —— 只记录不拦截。用于「对比实验」：看看不约束时模型会怎么偷懒。
    extra_allow:
        额外放行的工具名（谨慎使用，会削弱约束力）。
    extra_deny:
        额外禁止的工具名。
    """

    def __init__(
        self,
        mode: GuardMode = "enforce",
        extra_allow: Iterable[str] = (),
        extra_deny: Iterable[str] = (),
    ) -> None:
        self.mode: GuardMode = mode
        # 完整白名单 = 所有类别 + 额外放行
        self.allow: frozenset[str] = frozenset(
            name for group in ALLOWED_TOOLS.values() for name in group
        ) | frozenset(extra_allow)
        self.deny: dict[str, str] = {**FORBIDDEN_TOOLS}
        for name in extra_deny:
            self.deny[name] = "被显式禁止（配置项 extra_deny）。"
        self.violations: list[ViolationRecord] = []

    # -- 对外主接口 ---------------------------------------------------------
    def check(self, tool: str, args: dict[str, Any] | None = None, step: int | None = None) -> Action:
        """校验一个动作。通过则返回 :class:`Action`，否则抛 :class:`PolicyViolation`。"""
        args = dict(args or {})

        record = (
            self._check_denied(tool, args, step)
            or self._check_allowed(tool, args, step)
            or self._check_executable(tool, args, step)
        )
        if record is not None:
            self.violations.append(record)
            if self.mode == "enforce":
                raise PolicyViolation(record)
            # audit 模式：记下来但放行
        return Action(tool=tool, args=args)

    def check_context(self, window_title: str, step: int | None = None) -> ViolationRecord | None:
        """校验当前界面上下文。

        用于拦住「焦点在终端里还往里打字」这种隐蔽的偷懒方式。
        返回违规记录（若有），不抛异常——由调用方决定怎么处理。
        """
        if not looks_like_shell_window(window_title):
            return None
        record = ViolationRecord(
            step=step,
            tool="<context>",
            args={"window_title": window_title},
            rule="SHELL_WINDOW_FOCUS",
            reason=(
                f"当前焦点窗口「{window_title}」像是终端/解释器。"
                "在终端里输入等于执行命令，属于「捷径」。请切换到目标软件界面。"
            ),
        )
        self.violations.append(record)
        return record

    # -- 单条规则 -----------------------------------------------------------
    def _check_denied(self, tool: str, args: dict, step: int | None) -> ViolationRecord | None:
        """黑名单命中即拒绝。"""
        if tool in self.deny:
            return ViolationRecord(
                step=step,
                tool=tool,
                args=args,
                rule="FORBIDDEN_TOOL",
                reason=self.deny[tool],
            )
        return None

    def _check_allowed(self, tool: str, args: dict, step: int | None) -> ViolationRecord | None:
        """不在白名单里的一律拒绝（默认拒绝原则）。"""
        if not is_tool_allowed(tool) and tool not in self.allow:
            return ViolationRecord(
                step=step,
                tool=tool,
                args=args,
                rule="NOT_IN_ALLOWLIST",
                reason=(
                    f"「{tool}」不在界面操作白名单内。"
                    f"允许的动作只有：{', '.join(sorted(self.allow))}。"
                ),
            )
        return None

    def _check_executable(self, tool: str, args: dict, step: int | None) -> ViolationRecord | None:
        """参数级校验：启动的不能是 Shell / 解释器。"""
        if tool != "App":
            return None
        target = str(args.get("executable") or args.get("name") or "")
        if target and is_executable_forbidden(target):
            return ViolationRecord(
                step=step,
                tool=tool,
                args=args,
                rule="FORBIDDEN_EXECUTABLE",
                reason=(
                    f"不允许启动「{target}」——它是命令行/解释器，"
                    "等于开了一个可以绕过界面的后门。"
                ),
            )
        return None

    # -- 报告 ---------------------------------------------------------------
    @property
    def violation_count(self) -> int:
        return len(self.violations)

    def report(self) -> dict[str, Any]:
        """输出可序列化的约束报告，用于证据链与评测。"""
        return {
            "mode": self.mode,
            "allowed_tools": sorted(self.allow),
            "violation_count": self.violation_count,
            "violations": [
                {
                    "step": v.step,
                    "tool": v.tool,
                    "args": v.args,
                    "rule": v.rule,
                    "reason": v.reason,
                }
                for v in self.violations
            ],
        }
