"""策略层测试——这是本项目最该被测的部分。

如果约束可以被绕过，那整个项目就没有意义。所以这里的测试覆盖了
「模型可能尝试的各种偷懒方式」。
"""

from __future__ import annotations

import pytest

from true_hands.policy.guard import Guard, PolicyViolation
from true_hands.policy.rules import (
    ALLOWED_TOOLS,
    is_executable_forbidden,
    is_tool_allowed,
    looks_like_shell_window,
)


# ---------------------------------------------------------------------------
# 规则表本身
# ---------------------------------------------------------------------------
def test_allowed_and_forbidden_do_not_overlap() -> None:
    """白名单和黑名单不能有交集，否则规则自相矛盾。"""
    allowed = {name for group in ALLOWED_TOOLS.values() for name in group}
    from true_hands.policy.rules import FORBIDDEN_TOOLS

    assert not (allowed & set(FORBIDDEN_TOOLS)), "白名单与黑名单存在重叠项"


def test_gui_primitives_are_allowed() -> None:
    for tool in ("Screenshot", "Snapshot", "Click", "Type", "Shortcut", "App", "Wait"):
        assert is_tool_allowed(tool), f"{tool} 应当被允许"


def test_shortcuts_are_allowed_but_raw_clipboard_is_not() -> None:
    """Ctrl+V 是界面操作；直接读写剪贴板不是。"""
    assert is_tool_allowed("Shortcut")
    assert not is_tool_allowed("Clipboard")


@pytest.mark.parametrize(
    "exe",
    [
        r"C:\Windows\System32\cmd.exe",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "bash",
        r"C:\Python312\python.exe",
        "node.exe",
        "git",
    ],
)
def test_shell_and_interpreters_are_forbidden(exe: str) -> None:
    assert is_executable_forbidden(exe), f"{exe} 应当被禁止启动"


@pytest.mark.parametrize("title", ["命令提示符", "PowerShell", "Terminal", "Git Bash", "终端"])
def test_shell_window_detection(title: str) -> None:
    assert looks_like_shell_window(title)


def test_normal_window_is_not_flagged() -> None:
    assert not looks_like_shell_window("无标题 - 记事本")
    assert not looks_like_shell_window("Document1 - Microsoft Word")


# ---------------------------------------------------------------------------
# 网关行为
# ---------------------------------------------------------------------------
def test_guard_allows_gui_action() -> None:
    guard = Guard()
    action = guard.check("Type", {"text": "你好"}, step=0)
    assert action.tool == "Type"
    assert guard.violation_count == 0


def test_guard_blocks_file_write() -> None:
    """核心场景：模型想直接写文件，必须被拦下。"""
    guard = Guard()
    with pytest.raises(PolicyViolation) as exc:
        guard.check("FileSystem", {"mode": "write", "path": "桌面/a.docx"}, step=1)
    assert exc.value.record.rule == "FORBIDDEN_TOOL"
    assert "捷径" in exc.value.record.reason
    assert guard.violation_count == 1


def test_guard_blocks_shell() -> None:
    guard = Guard()
    with pytest.raises(PolicyViolation):
        guard.check("PowerShell", {"command": "echo hi > a.txt"})


def test_guard_blocks_unknown_tool_by_default() -> None:
    """默认拒绝原则：没在白名单里的，一律不行。"""
    guard = Guard()
    with pytest.raises(PolicyViolation) as exc:
        guard.check("SomeRandomTool", {})
    assert exc.value.record.rule == "NOT_IN_ALLOWLIST"


def test_guard_blocks_launching_shell_via_app() -> None:
    """光看动作名不够：App 是合法的，但不能拿它启动 cmd。"""
    guard = Guard()
    with pytest.raises(PolicyViolation) as exc:
        guard.check("App", {"executable": r"C:\Windows\System32\cmd.exe"}, step=2)
    assert exc.value.record.rule == "FORBIDDEN_EXECUTABLE"


def test_guard_allows_launching_normal_app() -> None:
    guard = Guard()
    action = guard.check("App", {"executable": r"C:\Windows\System32\notepad.exe"})
    assert action.tool == "App"


def test_audit_mode_records_but_does_not_block() -> None:
    """审计模式用于对比实验：看看不拦的话模型会怎么走。"""
    guard = Guard(mode="audit")
    action = guard.check("FileSystem", {"mode": "write", "path": "x"})
    assert action.tool == "FileSystem"
    assert guard.violation_count == 1


def test_context_check_flags_shell_window() -> None:
    guard = Guard()
    record = guard.check_context("Windows PowerShell", step=3)
    assert record is not None
    assert record.rule == "SHELL_WINDOW_FOCUS"


def test_report_is_serialisable() -> None:
    import json

    guard = Guard()
    with pytest.raises(PolicyViolation):
        guard.check("FileSystem", {"mode": "read", "path": "x"})
    payload = guard.report()
    json.dumps(payload)  # 不应抛异常
    assert payload["violation_count"] == 1
    assert payload["violations"][0]["tool"] == "FileSystem"
