"""命令行入口。

用法示例::

    # 在当前文件夹建立「只准操作界面」的约束
    true-hands project init

    # 看看当前目录落在哪个项目约束里
    true-hands project status

    # 查看约束规则
    true-hands policy

    # 空跑（不碰真实桌面）
    true-hands run --task write_article --driver mock

    # 用内置驱动真实执行（Windows 开箱可用，无需外部 MCP）
    true-hands run --task write_article \
        --title "My Article" --body "..." --driver native

    # 用 MCP 驱动执行（跨平台）
    true-hands run --task write_article \
        --driver mcp --driver-command computer-use-linux
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
from .driver.mock import MockDriver
from .driver.native import create_native_driver, native_available
from .evidence.recorder import RunRecorder
from .harness.loop import GUIOnlyHarness
from .model.provider import OpenAICompatProvider
from .policy.guard import Guard
from .policy.rules import ALLOWED_TOOLS, FORBIDDEN_TOOLS
from .project.scope import CONFIG_NAMES, ProjectScope, ScopeNotFound
from .tasks.write_article import build_write_article

load_dotenv()

app = typer.Typer(add_completion=False, help="强制 AI 只能通过真实操作图形界面完成任务。")
project_app = typer.Typer(help="管理「当前文件夹」的约束声明。")
app.add_typer(project_app, name="project")

console = Console()


# ---------------------------------------------------------------------------
@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"true-hands {__version__}")


@app.command()
def policy() -> None:
    """打印当前的约束规则（白名单 / 黑名单）。"""
    table = Table(title="✅ 允许的界面操作（白名单）")
    table.add_column("类别", style="cyan", no_wrap=True)
    table.add_column("动作")
    for group, tools in ALLOWED_TOOLS.items():
        table.add_row(group, ", ".join(tools))
    console.print(table)

    table2 = Table(title="⛔ 禁止的捷径（黑名单）")
    table2.add_column("动作", style="red", no_wrap=True)
    table2.add_column("理由")
    for tool, reason in FORBIDDEN_TOOLS.items():
        table2.add_row(tool, reason)
    console.print(table2)


# ---------------------------------------------------------------------------
@project_app.command("init")
def project_init(
    directory: str = typer.Option(".", help="在哪个目录建立约束（默认当前目录）"),
    mode: str = typer.Option("gui-only", help="gui-only / efficient / audit"),
    max_steps: int = typer.Option(60, help="该项目的最大步数"),
    note: str = typer.Option("", help="备注，例如「本项目内 Agent 只能操作界面」"),
    force: bool = typer.Option(False, "--force", help="覆盖已存在的配置"),
) -> None:
    """在当前文件夹写入 .true-hands.json，把这个文件夹变成受约束的项目。"""
    root = Path(directory).resolve()
    target = root / CONFIG_NAMES[0]
    if target.exists() and not force:
        console.print(f"[yellow]已存在 {target}，如需覆盖请加 --force[/yellow]")
        raise typer.Exit(code=1)

    scope = ProjectScope(
        root=root,
        config_path=target,
        enforce=True,
        mode=mode,
        max_steps=max_steps,
        require_gui_verification=True,
        note=note or "本项目内 Agent 只能通过直接操控电脑来完成任务。",
    )
    scope.save()
    console.print(Panel(scope.describe(), title=f"✅ 已建立项目约束：{target}", border_style="green"))
    console.print(
        "\n[dim]之后在这个文件夹（含子目录）里运行任何任务，都会自动套用这套约束。[/dim]"
    )


@project_app.command("status")
def project_status(
    directory: str = typer.Option(".", help="从哪个目录开始向上查找"),
) -> None:
    """显示当前目录落在哪个项目约束里。"""
    try:
        scope = ProjectScope.discover_or_raise(directory)
    except ScopeNotFound as exc:
        console.print(Panel(str(exc), title="⚠ 未找到项目约束", border_style="yellow"))
        raise typer.Exit(code=1)
    console.print(Panel(scope.describe(), title="当前项目约束", border_style="green"))


# ---------------------------------------------------------------------------
@app.command()
def run(
    task: str = typer.Option("write_article", help="任务名，目前支持 write_article"),
    title: str = typer.Option("Why GUI-Only Constraints Matter", help="文章标题"),
    body: str = typer.Option("", help="文章正文"),
    save_to: str = typer.Option("Desktop", help="保存位置描述"),
    driver: str = typer.Option("native", help="native（内置）/ mcp（外部服务器）/ mock（空跑）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="等价于 --driver mock"),
    audit: bool = typer.Option(False, "--audit", help="审计模式：违规只记录不拦截"),
    no_scope: bool = typer.Option(False, "--no-scope", help="忽略项目约束，使用默认策略"),
    max_steps: int = typer.Option(0, help="最大步数（0 表示沿用项目配置）"),
    driver_command: str = typer.Option("", help="MCP 驱动命令（--driver mcp 时必填）"),
    driver_arg: list[str] = typer.Option(None, "--driver-arg", help="传给驱动命令的参数，可重复"),
    runs_dir: str = typer.Option("runs", help="证据输出目录"),
) -> None:
    """执行一个任务。"""
    if task != "write_article":
        console.print(f"[red]暂不支持的任务：{task}[/red]")
        raise typer.Exit(code=2)

    # --- 1. 项目作用域 -----------------------------------------------------
    scope: ProjectScope | None = None
    if not no_scope:
        scope = ProjectScope.discover()
        if scope and scope.enforce:
            console.print(
                Panel(scope.describe(), title="🔒 已套用项目约束", border_style="green")
            )
        elif scope:
            console.print(f"[yellow]发现项目配置但未强制（enforce=false）：{scope.config_path}[/yellow]")
        else:
            console.print(
                "[dim]未发现项目约束。若希望这个文件夹内强制「只准操作界面」，"
                "运行：true-hands project init[/dim]"
            )

    # --- 2. 策略网关（项目优先） -------------------------------------------
    if scope and scope.enforce:
        guard = scope.build_guard()
    else:
        guard = Guard(mode="audit" if audit else "enforce")

    # --- 3. 驱动 -----------------------------------------------------------
    chosen = "mock" if dry_run else driver.lower()
    if chosen == "mock":
        active_driver = MockDriver()
        console.print("[yellow]⚠ 空跑模式：使用 mock 驱动，不会操作真实桌面。[/yellow]")
    elif chosen == "native":
        if not native_available():
            console.print("[red]当前平台没有内置原生驱动。[/red]请改用 --driver mcp。")
            raise typer.Exit(code=2)
        active_driver = create_native_driver(shot_dir=Path(runs_dir) / "_shots")
        console.print("[green]使用内置原生驱动（ctypes 直调系统 API）。[/green]")
    elif chosen == "mcp":
        from .driver.mcp_client import MCPDesktopDriver

        cmd = driver_command or os.getenv("GUI_DRIVER_COMMAND", "")
        if not cmd:
            console.print(
                "[red]--driver mcp 需要指定命令。[/red]用 --driver-command，"
                "或设置环境变量 GUI_DRIVER_COMMAND。"
            )
            raise typer.Exit(code=2)
        active_driver = MCPDesktopDriver(command=cmd, args=list(driver_arg or ["serve"]))
    else:
        console.print(f"[red]不认识的驱动：{driver}（可选 native / mcp / mock）[/red]")
        raise typer.Exit(code=2)

    # --- 4. 模型 -----------------------------------------------------------
    model = OpenAICompatProvider(
        model=os.getenv("MODEL_NAME", "gpt-4o"),
        allowed_tools=sorted(guard.allow),
    )

    # --- 5. 能力交叉检查 ---------------------------------------------------
    try:
        available = set(active_driver.list_tools())
    except Exception as exc:  # pragma: no cover - 取决于外部进程
        console.print(f"[red]驱动启动失败：{exc}[/red]")
        raise typer.Exit(code=3)
    usable, blocked = sorted(available & guard.allow), sorted(available - guard.allow)
    console.print(
        Panel(
            f"驱动提供 [green]{len(available)}[/green] 个工具，"
            f"策略放行 [green]{len(usable)}[/green] 个，拦截 [red]{len(blocked)}[/red] 个\n"
            f"被拦截：{', '.join(blocked) or '（无）'}",
            title="能力交叉检查",
        )
    )

    # --- 6. 执行 -----------------------------------------------------------
    task_obj = build_write_article(title=title, body=body or "(empty)", save_to=save_to)
    steps = max_steps or (scope.max_steps if scope else 40)
    recorder = RunRecorder(root=Path(runs_dir))
    harness = GUIOnlyHarness(
        driver=active_driver,
        guard=guard,
        model=model,
        recorder=recorder,
        max_steps=steps,
        on_step=lambda s, msg: console.print(f"  [dim]{s:02d}[/dim] {msg}"),
    )

    try:
        result = harness.run(task_obj)
    finally:
        active_driver.close()

    console.print(
        Panel(str(result), title="运行结论", border_style="green" if result.success else "red")
    )


if __name__ == "__main__":  # pragma: no cover
    app()
