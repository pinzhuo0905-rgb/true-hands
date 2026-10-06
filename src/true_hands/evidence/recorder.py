"""运行记录器：把每一步都落成可回放的证据。

产出目录结构::

    runs/<run-id>/
    ├── run.json          # 元信息 + 策略报告 + 最终结论
    ├── trace.jsonl       # 逐步骤动作轨迹（一行一步）
    └── shots/
        ├── step-000-before.png
        └── step-000-after.png

有了它，「这个结果是 GUI 产出的」就不再是一句口号，而是可以摆出来的证据。
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from ..driver.base import Observation


class RunRecorder:
    """记录一次完整运行。"""

    def __init__(self, root: str | Path = "runs", run_id: str | None = None) -> None:
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.dir = Path(root) / self.run_id
        self.shots = self.dir / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.dir / "trace.jsonl"
        self._steps = 0

    # -- 记录 ---------------------------------------------------------------
    def record_step(
        self,
        *,
        step: int,
        action: Any,
        result: Any,
        before: Observation | None = None,
        after: Observation | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        before_path = self._save_shot(before, f"step-{step:03d}-before")
        after_path = self._save_shot(after, f"step-{step:03d}-after")
        entry = {
            "step": step,
            "ts": time.time(),
            "action": {"tool": getattr(action, "tool", str(action)), "args": getattr(action, "args", {})},
            "ok": getattr(result, "ok", None),
            "detail": getattr(result, "detail", ""),
            "window": getattr(after or before, "window_title", ""),
            "shot_before": before_path,
            "shot_after": after_path,
        }
        if extra:
            entry.update(extra)
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._steps = max(self._steps, step + 1)

    def _save_shot(self, obs: Observation | None, name: str) -> str | None:
        if obs is None or not obs.screenshot_path:
            return None
        src = Path(obs.screenshot_path)
        if not src.exists():
            return None
        dst = self.shots / f"{name}{src.suffix or '.png'}"
        shutil.copyfile(src, dst)
        return str(dst.relative_to(self.dir))

    # -- 收尾 ---------------------------------------------------------------
    def finish(self, *, task: str, success: bool, policy_report: dict, summary: str = "") -> Path:
        payload = {
            "run_id": self.run_id,
            "task": task,
            "success": success,
            "steps": self._steps,
            "summary": summary,
            "policy": policy_report,
            "finished_at": time.time(),
        }
        out = self.dir / "run.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
