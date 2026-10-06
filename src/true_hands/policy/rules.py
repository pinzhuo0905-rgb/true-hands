"""约束规则表。

这是整个项目的「法律条文」——定义了什么算「真实界面操作」，
什么算「走后门」。改这里就等于改宪法，请谨慎。

设计原则：
    1. **白名单优先**：只有显式列出的动作才被允许，其余一律拒绝。
    2. **参数级校验**：光看动作名不够——`App` 可以启动记事本，也可以启动
       `cmd.exe`。所以要对参数再做一层检查。
    3. **可审计**：每一次拒绝都要能被解释清楚（reason 字段）。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 一、动作白名单：按类别组织的「界面操作原语」
# ---------------------------------------------------------------------------
# 命名与主流桌面 MCP 服务器（Windows-MCP / Cua Driver 等）保持一致，
# 便于直接对接。如果你的驱动用了别的名字，在 config 里做别名映射即可。
ALLOWED_TOOLS: dict[str, list[str]] = {
    # 观察：只能「看屏幕」，不能读文件
    "observe": ["Screenshot", "Snapshot", "DisplayInventory"],
    # 鼠标：像人一样点
    "mouse": ["Click", "Move", "Scroll", "MultiSelect"],
    # 键盘：像人一样敲
    "keyboard": ["Type", "Shortcut", "MultiEdit"],
    # 窗口：像人一样打开/切换软件
    "window": ["App"],
    # 节奏：等待界面响应
    "timing": ["Wait", "WaitFor"],
    # 桌面提示（无害）
    "notify": ["Notification"],
}

# 打平成集合，便于 O(1) 查询
ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(
    name for group in ALLOWED_TOOLS.values() for name in group
)


# ---------------------------------------------------------------------------
# 二、动作黑名单：这些是「捷径」，一旦出现即视为违规
# ---------------------------------------------------------------------------
# 注意：黑名单不是「白名单的补集」那么简单——它存在的意义是**给出明确的
# 拒绝理由**。当模型试图调用 write_file 时，我们要能告诉它：
# 「不行，因为这是文件写入，你必须打开编辑器在界面里写」。
FORBIDDEN_TOOLS: dict[str, str] = {
    "FileSystem": "文件读写属于「捷径」。请打开对应软件，在界面里操作。",
    "PowerShell": "命令执行属于「捷径」。请通过界面完成同样的操作。",
    "Registry": "注册表操作属于「捷径」。请通过系统设置界面完成。",
    "Process": "进程管理属于「捷径」。请通过任务管理器界面完成。",
    "Clipboard": "直接读写剪贴板绕过了界面。请用 Ctrl+C / Ctrl+V 快捷键。",
    "Scrape": "网络抓取属于「捷径」。请打开浏览器，从屏幕上读取内容。",
    "Write": "写文件属于「捷径」。",
    "Read": "读文件属于「捷径」。",
    "Bash": "Shell 属于「捷径」。",
    "Edit": "直接改文件属于「捷径」。",
}


# ---------------------------------------------------------------------------
# 三、参数级校验：光看动作名会漏
# ---------------------------------------------------------------------------
# `App` 是合法动作（人也要双击图标才能开软件），但它可以启动 cmd.exe，
# 那就等于开了一个 Shell 后门。所以对「要启动什么」再做一层限制。
FORBIDDEN_EXECUTABLES: tuple[str, ...] = (
    "cmd.exe", "cmd",
    "powershell.exe", "powershell", "pwsh.exe", "pwsh",
    "bash.exe", "bash", "sh.exe", "sh",
    "wsl.exe", "wsl",
    "python.exe", "python", "python3",
    "node.exe", "node",
    "perl.exe", "perl", "ruby.exe", "ruby",
    "cscript.exe", "wscript.exe", "mshta.exe",
    "reg.exe", "regedit.exe", "net.exe", "sc.exe",
    "curl.exe", "wget.exe", "ssh.exe", "scp.exe",
    "git.exe", "git",
)

# 窗口标题里出现这些词，说明当前焦点可能在终端里——
# 此时输入文字等价于「敲命令」，应该拦下来。
SHELL_WINDOW_HINTS: tuple[str, ...] = (
    "命令提示符", "cmd.exe", "Command Prompt",
    "PowerShell", "Windows PowerShell", "pwsh",
    "Terminal", "终端", "Git Bash", "WSL",
    "Python", "Node.js", "IDLE",
)


# ---------------------------------------------------------------------------
# 四、查询辅助
# ---------------------------------------------------------------------------
def is_tool_allowed(tool_name: str) -> bool:
    """动作名是否在白名单里。"""
    return tool_name in ALLOWED_TOOL_NAMES


def is_executable_forbidden(path_or_name: str) -> bool:
    """要启动的可执行文件是否属于禁止的 Shell / 解释器。

    同时接受 ``C:\\Windows\\System32\\cmd.exe`` 和 ``/usr/bin/bash`` 两种写法——
    不能依赖 ``os.path.basename``，因为它只认当前平台的分隔符，
    在 Linux 上遇到 Windows 路径会原样返回整串，从而漏判。
    """
    name = path_or_name.strip().strip('"').replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name in FORBIDDEN_EXECUTABLES


def looks_like_shell_window(window_title: str) -> bool:
    """窗口标题是否像是终端 / 解释器。"""
    title = window_title or ""
    return any(hint.lower() in title.lower() for hint in SHELL_WINDOW_HINTS)
