"""项目作用域：让约束跟着「文件夹」走。

## 为什么要这一层

「只准操作界面」如果只是个全局开关，就没法做到「这个项目要强制、那个项目不用」。
所以把约束写进**项目自己的配置文件**（放在文件夹根目录），程序启动时自动向上
查找、找到就生效。

这对应到实际使用就是：**某个文件夹（= 一次对话所绑定的项目）内，Agent 只能
通过直接操控电脑来干活。**

## 工作方式

```
D:\\work\\my-project\\        ← 这里有 .true-hands.json
├── .true-hands.json            ← 约束声明
├── src\\...
└── sub\\dir\\                  ← 在这里启动程序
```

程序从当前目录**逐级向上**找配置文件；找到 `my-project` 就停，加载它，
后续所有动作都受该项目的策略约束。找不到 → 退回默认策略（或拒绝启动）。

## 配置文件长这样

```json
{
  "enforce": true,
  "mode": "gui-only",
  "max_steps": 60,
  "require_gui_verification": true,
  "denied_tools": ["Clipboard"],
  "allowed_tools": [],
  "note": "本项目内 Agent 只能操作界面"
}
```
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..policy.guard import Guard

CONFIG_NAMES: tuple[str, ...] = (
    ".true-hands.json",
    ".true-hands.yaml",
    ".true-hands.yml",
)

#: 向上查找的最大层数，避免爬到盘根
MAX_WALK_UP = 24


class ScopeNotFound(Exception):
    """没有找到项目作用域配置。"""


@dataclass
class ProjectScope:
    """一个项目的约束声明。"""

    root: Path
    config_path: Path
    enforce: bool = True
    mode: str = "gui-only"
    """``gui-only`` 强制界面操作；``efficient`` 允许命令行；``audit`` 只记录不拦截。"""

    max_steps: int = 60
    require_gui_verification: bool = True
    allowed_tools: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()
    note: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    # -- 构造 ---------------------------------------------------------------
    @classmethod
    def load(cls, config_path: str | Path) -> "ProjectScope":
        """从配置文件加载。"""
        path = Path(config_path).resolve()
        if not path.exists():
            raise ScopeNotFound(f"配置文件不存在：{path}")
        data = _read_config(path)
        return cls(
            root=path.parent,
            config_path=path,
            enforce=bool(data.get("enforce", True)),
            mode=str(data.get("mode", "gui-only")),
            max_steps=int(data.get("max_steps", 60)),
            require_gui_verification=bool(data.get("require_gui_verification", True)),
            allowed_tools=tuple(data.get("allowed_tools") or ()),
            denied_tools=tuple(data.get("denied_tools") or ()),
            note=str(data.get("note", "")),
            raw=data,
        )

    @classmethod
    def discover(cls, start: str | Path | None = None) -> "ProjectScope | None":
        """从 ``start``（默认当前工作目录）逐级向上查找项目配置。

        返回最近的一个，找不到返回 ``None``。
        """
        current = Path(start or os.getcwd()).resolve()
        for _ in range(MAX_WALK_UP):
            for name in CONFIG_NAMES:
                candidate = current / name
                if candidate.is_file():
                    return cls.load(candidate)
            parent = current.parent
            if parent == current:  # 到盘根了
                break
            current = parent
        return None

    @classmethod
    def discover_or_raise(cls, start: str | Path | None = None) -> "ProjectScope":
        scope = cls.discover(start)
        if scope is None:
            raise ScopeNotFound(
                "当前目录及其上级都没有找到 "
                f"{' / '.join(CONFIG_NAMES)}。\n"
                "如果你希望这个文件夹内强制「只准操作界面」，"
                "请先运行：true-hands project init"
            )
        return scope

    # -- 写入 ---------------------------------------------------------------
    def save(self, path: str | Path | None = None) -> Path:
        """把当前作用域写回配置文件。"""
        target = Path(path) if path else self.config_path
        payload = {
            "enforce": self.enforce,
            "mode": self.mode,
            "max_steps": self.max_steps,
            "require_gui_verification": self.require_gui_verification,
            "allowed_tools": list(self.allowed_tools),
            "denied_tools": list(self.denied_tools),
            "note": self.note,
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return target

    # -- 应用 ---------------------------------------------------------------
    def build_guard(self) -> Guard:
        """按本项目的策略构造一个策略网关。"""
        guard_mode = "audit" if self.mode == "audit" or not self.enforce else "enforce"
        return Guard(
            mode=guard_mode,  # type: ignore[arg-type]
            extra_allow=self.allowed_tools,
            extra_deny=self.denied_tools,
        )

    def describe(self) -> str:
        lines = [
            f"项目根目录：{self.root}",
            f"配置文件：  {self.config_path.name}",
            f"强制约束：  {'是' if self.enforce else '否'}",
            f"模式：      {self.mode}",
            f"最大步数：  {self.max_steps}",
            f"界面验收：  {'必需' if self.require_gui_verification else '可选'}",
        ]
        if self.denied_tools:
            lines.append(f"额外禁止：  {', '.join(self.denied_tools)}")
        if self.allowed_tools:
            lines.append(f"额外放行：  {', '.join(self.allowed_tools)}")
        if self.note:
            lines.append(f"备注：      {self.note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
def _read_config(path: Path) -> dict[str, Any]:
    """读配置。JSON 永远支持；YAML 需要装 PyYAML 才支持。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text) or {}
    # YAML
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise ScopeNotFound(
            f"{path.name} 是 YAML 格式，但未安装 PyYAML。\n"
            "请执行 pip install pyyaml，或改用 .true-hands.json。"
        ) from exc
    return yaml.safe_load(text) or {}
