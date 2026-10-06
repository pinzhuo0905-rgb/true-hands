"""MCP 桌面驱动：通过 Model Context Protocol 操控真实桌面。

支持任何符合 MCP 标准的桌面服务器，例如：

* Windows-MCP      https://github.com/CursorTouch/Windows-MCP
* Cua Driver       https://github.com/trycua/cua
* computer-use-linux  https://github.com/agent-sh/computer-use-linux
* agent-desktop    https://github.com/lahfir/agent-desktop

实现要点：手写一个极简的 stdio JSON-RPC 客户端，不引入额外的 MCP SDK
依赖，保证「看得懂、改得动」。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from ..policy.guard import Action
from .base import ActionResult, Observation

DEFAULT_TIMEOUT = 60.0


class MCPError(RuntimeError):
    """MCP 通信或调用失败。"""


class MCPDesktopDriver:
    """通过 stdio 与一个 MCP 桌面服务器通信。"""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.timeout = timeout
        self._env = {**os.environ, **(env or {})}
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._tools: list[str] = []
        self._server_info: dict[str, Any] = {}

    # -- 生命周期 -----------------------------------------------------------
    def start(self) -> None:
        """启动服务器进程并完成 MCP 握手。"""
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=self._env,
        )
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "true-hands", "version": "0.1.0"},
            },
        )
        self._server_info = result.get("serverInfo", {})
        self._notify("notifications/initialized", {})
        self._refresh_tools()

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin and self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
        finally:
            self._proc = None

    def __enter__(self) -> "MCPDesktopDriver":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- Driver 接口 --------------------------------------------------------
    def list_tools(self) -> list[str]:
        return list(self._tools)

    def observe(self) -> Observation:
        """优先用 Snapshot（带无障碍元素），失败则退回 Screenshot。"""
        for tool in ("Snapshot", "Screenshot"):
            if tool not in self._tools:
                continue
            try:
                payload = self._call_tool(tool, {})
            except MCPError:
                continue
            return self._to_observation(payload, tool)
        raise MCPError("驱动没有提供 Snapshot 或 Screenshot，无法观察屏幕。")

    def act(self, action: Action) -> ActionResult:
        """执行动作。**调用方必须保证已通过 Guard 校验。**"""
        try:
            payload = self._call_tool(action.tool, action.args)
        except MCPError as exc:
            return ActionResult(ok=False, detail=str(exc))
        detail = _summarise(payload)
        return ActionResult(ok=True, detail=detail)

    # -- 内部：MCP 协议 -----------------------------------------------------
    def _refresh_tools(self) -> None:
        result = self._request("tools/list", {})
        self._tools = [t.get("name", "") for t in result.get("tools", [])]

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise MCPError(f"驱动不提供工具「{name}」。可用：{', '.join(self._tools)}")
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            message = self._read_until_id(req_id)
        if "error" in message:
            err = message["error"]
            raise MCPError(f"{method} 失败：{err.get('message', err)}")
        return message.get("result", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError("服务器未启动。")
        self._proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def _read_until_id(self, req_id: int) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise MCPError("服务器进程已退出。")
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # 服务器可能往 stdout 打了日志，跳过
            if message.get("id") == req_id:
                return message

    # -- 内部：结果转换 -----------------------------------------------------
    @staticmethod
    def _to_observation(payload: dict[str, Any], tool: str) -> Observation:
        obs = Observation(raw=payload, window_title=str(payload.get("active_window", "")))
        for block in payload.get("content", []) or []:
            if block.get("type") == "text":
                obs.elements.append({"role": tool, "name": block.get("text", "")[:500]})
            elif block.get("type") == "image":
                obs.screenshot_path = block.get("path") or block.get("data")
        return obs


def _summarise(payload: dict[str, Any]) -> str:
    """把工具返回压成一句人能读的话。"""
    if isinstance(payload, dict):
        if "content" in payload:
            texts = [
                b.get("text", "")
                for b in payload["content"]
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = " ".join(t for t in texts if t).strip()
            if joined:
                return joined[:300]
        if "isError" in payload:
            return f"isError={payload['isError']}"
    return json.dumps(payload, ensure_ascii=False)[:300]
