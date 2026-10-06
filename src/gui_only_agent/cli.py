"""命令行入口。

用法示例::

    # 查看当前的约束规则
    gui-only-agent policy

    # 空跑（用 mock 驱动，不碰真实桌面，验证流程是否通）
    gui-only-agent run --task write_article --dry-run

    # 真实执行
    gui-only-agent run --task write_article \
        --title "我的文章" --body "正文内容……" \
        --driver-command "C:\\Users\\me\\.local\\bin\\windows-mcp.exe" \
        --driver-arg serve
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .driver.mcp_client import MCPDesktopDriver
from .driver.mock import MockDriver
from .evidence.recorder import RunRecorder
from .harness.loop import GUIOnlyHarness
from .model.provider import OpenAICompatProvider
from .policy.guard import Guard
from .policy.rules import ALLOWED_TOOLS, FORBIDDEN_TOOLS
from .tasks.write_article import build_write_article

load_dotenv()

app = typer.Typer(add_completion=False, help="强制 AI 只能通过真实操作图形界面完成任务。")
console = Console()


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"gui-only-agent {__version__}")


@app.command()
def policy() -> None:
    """打印当前的约束规则（白名单 / 黑名单）。"""
    table = Table(title="✅ 允许的界面操作（白名单）", show_lines=False)
    table.add_column("类别", style="cyan", no_wrap=True)
    table.add_column("动作")
    for group, tools in ALLOWED_TOOLS.items():
        table.add_row(group, ", ".join(tools))
    console.print(table)

    table2 = Table(title="⛔ 禁止的捷径（黑名单）", show_lines=False)
    table2.add_column("动作", style="red", no_wrap=True)
    table2.add_column("理由")
    for tool, reason in FORBIDDEN_TOOLS.items():
        table2.add_row(tool, reason)
    console.print(table2)


@app.command()
def run(
    task: str = typer.Option("write_article", help="任务名，目前支持 write_article"),
    title: str = typer.Option("论界面操作的必要性", help="文章标题"),
    body: str = typer.Option("", help="文章正文"),
    save_to: str = typer.Option("桌面", help="保存位置描述"),
    dry_run: bool = typer.Option(False, "--dry-run", help="用 mock 驱动空跑，不碰真实桌面"),
    audit: bool = typer.Option(False, "--audit", help="审计模式：违规只记录不拦截（用于对比）"),
    max_steps: int = typer.Option(40, help="最大步数"),
    driver_command: str = typer.Option("", help="MCP 桌面服务器命令（如 windows-mcp.exe）"),
    driver_arg: list[str] = typer.Option(None, "--driver-arg", help="传给驱动命令的参数，可重复"),
    runs_dir: str = typer.Option("runs", help="证据输出目录"),
) -> None:
    """执行一个任务。"""
    if task != "write_article":
        console.print(f"[red]暂不支持的任务：{task}[/red]")
        raise typer.Exit(code=2)

    task_obj = build_write_article(title=title, body=body or "（正文为空）", save_to=save_to)

    # --- 驱动 ---
    if dry_run:
        driver = MockDriver()
        console.print("[yellow]⚠ 空跑模式：使用 mock 驱动，不会操作真实桌面。[/yellow]")
    else:
        cmd = driver_command or os.getenv("GUI_DRIVER_COMMAND", "")
        if not cmd:
            console.print(
                "[red]未指定驱动命令。[/red]请用 --driver-command 指定，"
                "或设置环境变量 GUI_DRIVER_COMMAND。\n"
                "例如：--driver-command \"C:\\Users\\me\\.local\\bin\\windows-mcp.exe\" --driver-arg serve"
            )
            raise typer.Exit(code=2)
        driver = MCPDesktopDriver(command=cmd, args=list(driver_arg or ["serve"]))

    # --- 策略网关 ---
    guard = Guard(mode="audit" if audit else "enforce")

    # --- 模型 ---
    model = OpenAICompatProvider(
        model=os.getenv("MODEL_NAME", "gpt-4o"),
        allowed_tools=sorted(guard.allow),
    )

    # --- 交叉检查：驱动能力 ∩ 策略白名单 ---
    try:
        available = set(driver.list_tools())
    except Exception as exc:  # pragma: no cover - 取决于外部进程
        console.print(f"[red]驱动启动失败：{exc}[/red]")
        raise typer.Exit(code=3)
    usable = sorted(available & guard.allow)
    blocked = sorted(available - guard.allow)
    console.print(
        Panel(
            f"驱动提供 [green]{len(available)}[/green] 个工具，"
            f"策略放行 [green]{len(usable)}[/green] 个，"
            f"拦截 [red]{len(blocked)}[/red] 个\n"
            f"被拦截：{', '.join(blocked) or '（无）'}",
            title="能力交叉检查",
        )
    )

    # --- 执行 ---
    recorder = RunRecorder(root=Path(runs_dir))
    harness = GUIOnlyHarness(
        driver=driver,
        guard=guard,
        model=model,
        recorder=recorder,
        max_steps=max_steps,
        on_step=lambda step, msg: console.print(f"  [dim]{step:02d}[/dim] {msg}"),
    )

    try:
        result = harness.run(task_obj)
    finally:
        driver.close()

    console.print(Panel(str(result), title="运行结论", border_style="green" if result.success else "red"))


if __name__ == "__main__":  # pragma: no cover
    app()
