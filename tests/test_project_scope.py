"""项目作用域测试：约束是否真的跟着文件夹走。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gui_only_agent.policy.guard import Guard, PolicyViolation
from gui_only_agent.project.scope import CONFIG_NAMES, ProjectScope, ScopeNotFound


def _make_project(root: Path, **overrides) -> ProjectScope:
    root.mkdir(parents=True, exist_ok=True)
    cfg = root / CONFIG_NAMES[0]
    defaults = dict(
        root=root,
        config_path=cfg,
        enforce=True,
        mode="gui-only",
        max_steps=60,
        require_gui_verification=True,
        note="本项目内 Agent 只能操作界面",
    )
    defaults.update(overrides)
    scope = ProjectScope(**defaults)  # type: ignore[arg-type]
    scope.save()
    return scope


# ---------------------------------------------------------------------------
def test_no_config_returns_none(tmp_path: Path) -> None:
    assert ProjectScope.discover(tmp_path) is None


def test_discover_from_nested_dir(tmp_path: Path) -> None:
    """核心行为：从任意深度的子目录都能找到项目根。"""
    project = tmp_path / "my-project"
    _make_project(project)
    deep = project / "src" / "a" / "b" / "c"
    deep.mkdir(parents=True)

    found = ProjectScope.discover(deep)
    assert found is not None
    assert found.root == project
    assert found.mode == "gui-only"


def test_discover_stops_at_nearest_config(tmp_path: Path) -> None:
    """嵌套项目时，取最近的那一个。"""
    outer = tmp_path / "outer"
    inner = outer / "packages" / "inner"
    _make_project(outer, max_steps=10)
    _make_project(inner, max_steps=99)

    found = ProjectScope.discover(inner)
    assert found is not None
    assert found.root == inner
    assert found.max_steps == 99


def test_discover_or_raise_gives_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(ScopeNotFound) as exc:
        ProjectScope.discover_or_raise(tmp_path)
    assert "project init" in str(exc.value)


def test_roundtrip_preserves_fields(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project, max_steps=77, denied_tools=("Clipboard",), note="hello")
    loaded = ProjectScope.discover(project)
    assert loaded is not None
    assert loaded.max_steps == 77
    assert loaded.denied_tools == ("Clipboard",)
    assert loaded.note == "hello"


def test_scope_builds_enforcing_guard(tmp_path: Path) -> None:
    """项目约束下的网关必须真的拦得住。"""
    project = tmp_path / "p"
    _make_project(project, mode="gui-only")
    guard = ProjectScope.discover(project).build_guard()  # type: ignore[union-attr]

    assert guard.mode == "enforce"
    with pytest.raises(PolicyViolation):
        guard.check("FileSystem", {"mode": "write", "path": "x"})


def test_audit_mode_project_does_not_block(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project, mode="audit")
    guard = ProjectScope.discover(project).build_guard()  # type: ignore[union-attr]
    assert guard.mode == "audit"
    guard.check("PowerShell", {"command": "x"})
    assert guard.violation_count == 1


def test_enforce_false_downgrades_to_audit(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project, enforce=False, mode="gui-only")
    scope = ProjectScope.discover(project)
    assert scope is not None and scope.enforce is False
    assert scope.build_guard().mode == "audit"


def test_project_can_deny_extra_tools(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project, denied_tools=("Clipboard",))
    guard = ProjectScope.discover(project).build_guard()  # type: ignore[union-attr]
    with pytest.raises(PolicyViolation) as exc:
        guard.check("Clipboard", {"mode": "get"})
    assert exc.value.record.rule == "FORBIDDEN_TOOL"


def test_project_can_allow_extra_tools(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project, allowed_tools=("CustomGuiTool",))
    guard = ProjectScope.discover(project).build_guard()  # type: ignore[union-attr]
    action = guard.check("CustomGuiTool", {})
    assert action.tool == "CustomGuiTool"


def test_config_file_is_valid_json(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _make_project(project)
    payload = json.loads((project / CONFIG_NAMES[0]).read_text(encoding="utf-8"))
    assert payload["mode"] == "gui-only"
    assert payload["enforce"] is True


def test_default_guard_is_still_strict() -> None:
    """没套项目约束时，默认策略同样严格。"""
    guard = Guard()
    with pytest.raises(PolicyViolation):
        guard.check("FileSystem", {"mode": "read", "path": "x"})
