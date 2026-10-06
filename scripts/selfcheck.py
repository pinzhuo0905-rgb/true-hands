"""零依赖自检脚本：不装 pytest 也能验证约束是否真的拦得住。

用法：
    PYTHONPATH=src python scripts/selfcheck.py
"""

from __future__ import annotations

import sys
import traceback

from true_hands.policy.guard import Guard, PolicyViolation
from true_hands.policy.rules import (
    ALLOWED_TOOLS,
    FORBIDDEN_TOOLS,
    is_executable_forbidden,
    is_tool_allowed,
    looks_like_shell_window,
)

# Windows 控制台默认编码不是 UTF-8，直接 print "✓" 会抛 UnicodeEncodeError。
# CI 的 windows-latest 就是这样挂的，所以这里先把标准流切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PASS, FAIL = 0, 0


def check(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \u2713 {name}")
    else:
        FAIL += 1
        print(f"  \u2717 {name}   <-- 失败")


def main() -> int:
    print("=" * 64)
    print("true-hands 约束层自检")
    print("=" * 64)

    print("\n[1] 规则表自洽")
    allowed = {n for g in ALLOWED_TOOLS.values() for n in g}
    check("白名单与黑名单无重叠", not (allowed & set(FORBIDDEN_TOOLS)))
    check("界面原语被放行（Screenshot/Click/Type/App）",
          all(is_tool_allowed(t) for t in ("Screenshot", "Click", "Type", "App", "Shortcut")))
    check("文件写入不在白名单", not is_tool_allowed("FileSystem"))
    check("Ctrl+V 走 Shortcut（允许），裸 Clipboard 不允许",
          is_tool_allowed("Shortcut") and not is_tool_allowed("Clipboard"))

    print("\n[2] 启动目标校验")
    for exe in (r"C:\Windows\System32\cmd.exe", "powershell.exe", "bash",
                r"C:\Python312\python.exe", "node.exe", "git"):
        check(f"禁止启动 {exe}", is_executable_forbidden(exe))
    check("允许启动记事本", not is_executable_forbidden(r"C:\Windows\System32\notepad.exe"))

    print("\n[3] 终端窗口识别")
    for title in ("命令提示符", "PowerShell", "Terminal", "Git Bash", "终端"):
        check(f"识别终端窗口：{title}", looks_like_shell_window(title))
    check("不误判记事本", not looks_like_shell_window("无标题 - 记事本"))
    check("不误判 Word", not looks_like_shell_window("Document1 - Microsoft Word"))

    print("\n[4] 网关拦截行为")
    g = Guard()
    g.check("Type", {"text": "你好"}, step=0)
    check("放行合法界面动作 Type", g.violation_count == 0)

    try:
        g.check("FileSystem", {"mode": "write", "path": "桌面/a.docx"}, step=1)
        check("拦截 FileSystem 写文件", False)
    except PolicyViolation as e:
        check("拦截 FileSystem 写文件", e.record.rule == "FORBIDDEN_TOOL")
        print(f"      拒绝理由：{e.record.reason}")

    try:
        g.check("PowerShell", {"command": "echo x > a.txt"}, step=2)
        check("拦截 PowerShell", False)
    except PolicyViolation:
        check("拦截 PowerShell", True)

    try:
        g.check("SomeRandomTool", {}, step=3)
        check("默认拒绝未知动作", False)
    except PolicyViolation as e:
        check("默认拒绝未知动作", e.record.rule == "NOT_IN_ALLOWLIST")

    try:
        g.check("App", {"executable": r"C:\Windows\System32\cmd.exe"}, step=4)
        check("拦截用 App 启动 cmd（参数级校验）", False)
    except PolicyViolation as e:
        check("拦截用 App 启动 cmd（参数级校验）", e.record.rule == "FORBIDDEN_EXECUTABLE")

    ok = g.check("App", {"executable": r"C:\Windows\System32\notepad.exe"})
    check("放行启动记事本", ok.tool == "App")

    check("累计违规数 = 4", g.violation_count == 4)

    print("\n[5] 上下文校验（焦点在终端）")
    g2 = Guard()
    rec = g2.check_context("Windows PowerShell", step=0)
    check("识别焦点落在终端并告警", rec is not None and rec.rule == "SHELL_WINDOW_FOCUS")
    check("普通窗口不告警", g2.check_context("Document1 - Microsoft Word") is None)

    print("\n[6] 审计模式（只记录不拦截）")
    g3 = Guard(mode="audit")
    a = g3.check("FileSystem", {"mode": "write", "path": "x"})
    check("审计模式放行但记账", a.tool == "FileSystem" and g3.violation_count == 1)

    print("\n[7] 报告可序列化")
    import json
    json.dumps(g.report())
    check("guard.report() 可 JSON 序列化", True)

    # ---------------------------------------------------------------
    print("\n[8] 决策循环（mock 驱动，不碰真实桌面）")
    from true_hands.driver.mock import MockDriver
    from true_hands.harness.loop import GUIOnlyHarness
    from true_hands.model.provider import Decision
    from true_hands.tasks.write_article import build_write_article

    class ScriptedModel:
        def __init__(self, script):
            self.script = list(script)

        def decide(self, task_prompt, observation, history):
            return self.script.pop(0) if self.script else Decision(done=True, thought="结束")

    # 8.1 正常路径
    driver = MockDriver()
    guard = Guard()
    model = ScriptedModel([
        Decision(tool="App", args={"name": "notepad"}),
        Decision(tool="Type", args={"text": "正文"}),
        Decision(tool="Shortcut", args={"shortcut": "ctrl+s"}),
        Decision(done=True, thought="已保存"),
    ])
    GUIOnlyHarness(driver=driver, guard=guard, model=model, max_steps=10).run(
        build_write_article("标题", "正文")
    )
    check("正常路径下动作按序执行",
          [a.tool for a in driver.executed] == ["App", "Type", "Shortcut"])
    check("正常路径无违规", guard.violation_count == 0)

    # 8.2 偷懒被拦
    driver2 = MockDriver()
    guard2 = Guard()
    model2 = ScriptedModel([
        Decision(tool="FileSystem", args={"mode": "write", "path": "桌面/a.docx"}),
        Decision(tool="Type", args={"text": "改用界面输入"}),
        Decision(done=True, thought="改正后完成"),
    ])
    res2 = GUIOnlyHarness(driver=driver2, guard=guard2, model=model2, max_steps=10).run(
        build_write_article("标题", "正文")
    )
    check("偷懒动作没有被执行", "FileSystem" not in [a.tool for a in driver2.executed])
    check("但被记入违规", res2.policy_report["violation_count"] == 1)
    check("违规规则正确", res2.policy_report["violations"][0]["rule"] == "FORBIDDEN_TOOL")

    # 8.3 连续偷懒中止
    cheat = Decision(tool="PowerShell", args={"command": "echo x > a.txt"})
    guard3 = Guard()
    res3 = GUIOnlyHarness(
        driver=MockDriver(), guard=guard3,
        model=ScriptedModel([cheat] * 6), max_steps=10,
    ).run(build_write_article("标题", "正文"))
    check("连续偷懒会中止", res3.success is False and "中止" in res3.summary)

    print("\n[9] 项目作用域（约束跟着文件夹走）")
    import tempfile
    from pathlib import Path

    from true_hands.project.scope import ProjectScope

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "my-project"
        nested = root / "src" / "deep"
        nested.mkdir(parents=True)

        # 9.1 没配置时找不到
        try:
            ProjectScope.discover(nested)
            check("无配置时返回 None", ProjectScope.discover(nested) is None)
        except Exception:
            check("无配置时返回 None", False)

        # 9.2 建立约束
        cfg = root / ".true-hands.json"
        scope = ProjectScope(
            root=root, config_path=cfg, enforce=True, mode="gui-only",
            max_steps=77, note="本项目内 Agent 只能操作界面",
        )
        scope.save()
        check("配置文件已写入", cfg.is_file())

        # 9.3 从深层子目录能向上找到
        found = ProjectScope.discover(nested)
        check("从子目录向上找到项目约束", found is not None)
        check("定位到正确的项目根", found is not None and found.root == root)
        check("读取到 max_steps", found is not None and found.max_steps == 77)
        check("读取到 mode", found is not None and found.mode == "gui-only")

        # 9.4 约束真的生效：网关按项目模式构造
        g_scope = found.build_guard() if found else Guard()
        check("项目约束下网关为 enforce", g_scope.mode == "enforce")
        try:
            g_scope.check("FileSystem", {"mode": "write", "path": "x"})
            check("项目约束下仍拦截写文件", False)
        except PolicyViolation:
            check("项目约束下仍拦截写文件", True)

        # 9.5 审计模式的项目
        audit_cfg = Path(tmp) / "audit-project" / ".true-hands.json"
        audit_cfg.parent.mkdir(parents=True)
        ProjectScope(
            root=audit_cfg.parent, config_path=audit_cfg,
            enforce=True, mode="audit",
        ).save()
        g_audit = ProjectScope.discover(audit_cfg.parent).build_guard()
        check("audit 模式项目放行但记账", g_audit.mode == "audit")

        # 9.6 enforce=false 时不强制
        off_cfg = Path(tmp) / "free-project" / ".true-hands.json"
        off_cfg.parent.mkdir(parents=True)
        ProjectScope(
            root=off_cfg.parent, config_path=off_cfg, enforce=False,
        ).save()
        off = ProjectScope.discover(off_cfg.parent)
        check("enforce=false 被正确读取", off is not None and off.enforce is False)

    print("\n" + "=" * 64)
    print(f"结果：通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
