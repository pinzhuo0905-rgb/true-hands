"""端到端流程测试：用 mock 驱动跑通「观察-决策-执行-验收」。"""

from __future__ import annotations

from true_hands.driver.mock import MockDriver
from true_hands.harness.loop import GUIOnlyHarness
from true_hands.model.provider import Decision
from true_hands.policy.guard import Guard
from true_hands.tasks.write_article import build_write_article


class ScriptedModel:
    """按剧本输出动作的假模型，用于测试循环本身。"""

    def __init__(self, script: list[Decision]) -> None:
        self.script = list(script)
        self.calls = 0

    def decide(self, task_prompt, observation, history):
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return Decision(done=True, thought="剧本结束")


def test_loop_executes_gui_actions() -> None:
    model = ScriptedModel(
        [
            Decision(tool="App", args={"name": "notepad"}),
            Decision(tool="Type", args={"text": "正文"}),
            Decision(tool="Shortcut", args={"shortcut": "ctrl+s"}),
            Decision(done=True, thought="已保存"),
        ]
    )
    driver = MockDriver()
    guard = Guard()
    harness = GUIOnlyHarness(driver=driver, guard=guard, model=model, max_steps=10)
    result = harness.run(build_write_article("标题", "正文"))

    assert [a.tool for a in driver.executed] == ["App", "Type", "Shortcut"]
    assert guard.violation_count == 0
    assert result.policy_report["violation_count"] == 0


def test_loop_feeds_rejection_back_to_model() -> None:
    """模型偷懒时，拒绝理由要回灌，让它改正。"""
    model = ScriptedModel(
        [
            Decision(tool="FileSystem", args={"mode": "write", "path": "桌面/a.docx"}),
            Decision(tool="Type", args={"text": "改用界面输入"}),
            Decision(done=True, thought="改正后完成"),
        ]
    )
    driver = MockDriver()
    guard = Guard()
    harness = GUIOnlyHarness(driver=driver, guard=guard, model=model, max_steps=10)
    result = harness.run(build_write_article("标题", "正文"))

    # 偷懒的动作没有被执行
    assert "FileSystem" not in [a.tool for a in driver.executed]
    # 但被记了一笔
    assert result.policy_report["violation_count"] == 1
    assert result.policy_report["violations"][0]["rule"] == "FORBIDDEN_TOOL"


def test_loop_aborts_on_repeated_cheating() -> None:
    """连续偷懒要中止，不能无限重试。"""
    cheat = Decision(tool="PowerShell", args={"command": "echo x > a.txt"})
    model = ScriptedModel([cheat, cheat, cheat, cheat, cheat, cheat])
    guard = Guard()
    harness = GUIOnlyHarness(driver=MockDriver(), guard=guard, model=model, max_steps=10)
    result = harness.run(build_write_article("标题", "正文"))

    assert result.success is False
    assert "中止" in result.summary
