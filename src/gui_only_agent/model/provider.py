"""模型提供方：统一「给定观察 → 输出动作」的接口。

内置一个 OpenAI 兼容实现（可直接对接 OpenAI / DeepSeek / 通义 / 本地 vLLM 等），
你也可以换成任何别的模型——只要实现 :class:`ModelProvider`。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..driver.base import Observation


@dataclass
class Decision:
    """模型给出的下一步决定。"""

    done: bool = False
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    thought: str = ""
    raw: str = ""

    @classmethod
    def from_json(cls, text: str) -> "Decision":
        """从模型输出里抠出 JSON（容忍 ```json 代码块）。"""
        cleaned = text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    cleaned = candidate
                    break
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return cls(done=False, tool="", args={}, raw=text, thought="(解析失败)")
        return cls(
            done=bool(data.get("done", False)),
            tool=str(data.get("tool", "")),
            args=dict(data.get("args") or {}),
            thought=str(data.get("thought", "")),
            raw=text,
        )


class ModelProvider(Protocol):
    def decide(self, task_prompt: str, observation: Observation, history: list[str]) -> Decision:
        ...


SYSTEM_PROMPT = """你是一个「只能通过操作图形界面完成任务」的智能体。

硬性约束（违反会被系统拒绝，不会执行）：
- 你只能使用这些动作：{tools}
- 你**不能**读写文件、不能执行命令、不能调用接口、不能直接操作剪贴板
- 想写文章，就打开文字处理软件，在界面里一个字一个字地打
- 想保存，就按 Ctrl+S，在弹窗里选路径、点保存
- 想确认结果，就再看一次屏幕（截图），不要试图去读文件

每一步只输出一个 JSON 动作：
{{"thought": "简短的判断", "tool": "动作名", "args": {{...}}}}

任务完成时输出：
{{"thought": "为什么认为完成了", "done": true}}
"""


class OpenAICompatProvider:
    """OpenAI 兼容的模型提供方。"""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        allowed_tools: list[str] | None = None,
        temperature: float = 0.0,
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.allowed_tools = allowed_tools or []
        self.temperature = temperature
        self.timeout = timeout

    def decide(self, task_prompt: str, observation: Observation, history: list[str]) -> Decision:
        # 延迟导入：不用这个 Provider 的人不必装 httpx
        import httpx

        system = SYSTEM_PROMPT.format(tools=", ".join(self.allowed_tools))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"任务：{task_prompt}"},
        ]
        if history:
            messages.append({"role": "user", "content": "已完成步骤：\n" + "\n".join(history[-20:])})
        messages.append({"role": "user", "content": "当前屏幕状态：\n" + observation.to_prompt()})
        messages.append({"role": "user", "content": "请输出下一步动作的 JSON。"})

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "messages": messages, "temperature": self.temperature},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return Decision.from_json(text)
