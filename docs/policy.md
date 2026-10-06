# 约束规范

这份文档定义「什么算真实界面操作」。它是 `policy/rules.py` 的自然语言版本。

## 判定原则

一个问题就能判断：**一个正常人坐在电脑前，能不能只靠眼睛和手完成这件事？**

- 能 → 属于界面操作
- 需要写代码 / 开命令行 / 调接口 → 属于捷径

## ✅ 允许（界面操作）

| 动作 | 说明 | 类比人的行为 |
|---|---|---|
| `Screenshot` / `Snapshot` | 看屏幕 | 抬头看显示器 |
| `DisplayInventory` | 看有几个显示器 | 知道自己在哪块屏上操作 |
| `Click` / `MultiSelect` | 点击 | 动鼠标点 |
| `Move` / `Scroll` | 移动 / 滚动 | 移动鼠标、滚轮 |
| `Type` / `MultiEdit` | 输入文字 | 敲键盘 |
| `Shortcut` | 快捷键（Ctrl+C / Ctrl+S…） | 按组合键 |
| `App` | 打开 / 切换软件 | 双击图标、Alt+Tab |
| `Wait` / `WaitFor` | 等界面响应 | 等软件加载 |
| `Notification` | 弹个提示 | — |

## ⛔ 禁止（捷径）

| 动作 | 为什么禁止 | 应该改成 |
|---|---|---|
| `FileSystem` | 直接读写文件，跳过了软件 | 打开编辑器，在界面里操作 |
| `PowerShell` / `Bash` | 执行命令，等于绕过一切界面 | 用界面完成同样的事 |
| `Registry` | 直接改注册表 | 打开系统设置界面 |
| `Process` | 直接管理进程 | 用任务管理器界面 |
| `Clipboard` | 直接读写剪贴板，绕过界面 | 用 Ctrl+C / Ctrl+V |
| `Scrape` | 网络抓取，跳过了浏览器 | 打开浏览器从屏幕读 |
| `Write` / `Read` / `Edit` | 文件工具 | 同 FileSystem |

## ⚠️ 参数级限制

### 1. 启动目标白名单化

`App` 是允许的，但**不能用来启动**：

```
cmd.exe / powershell.exe / pwsh.exe / bash.exe / wsl.exe
python.exe / node.exe / perl.exe / ruby.exe
cscript.exe / wscript.exe / mshta.exe
reg.exe / regedit.exe / net.exe / sc.exe
curl.exe / wget.exe / ssh.exe / scp.exe / git.exe
```

理由：这些等于「开一个可以绕过界面的后门」。

### 2. 上下文限制

当焦点窗口标题命中以下关键词时发出违规警告：

```
命令提示符 / cmd.exe / Command Prompt
PowerShell / pwsh / Terminal / 终端
Git Bash / WSL / Python / Node.js / IDLE
```

理由：**在终端里输入文字 = 执行命令**。这是最隐蔽的绕过方式。

## 模式说明

| 模式 | 行为 | 用途 |
|---|---|---|
| `enforce`（默认） | 违规直接抛异常，动作不执行 | 正常使用 |
| `audit` | 违规只记录，动作仍执行 | **对比实验**：看看不约束时模型会怎么偷懒 |

## 如何新增规则

1. 在 `rules.py` 里改白名单 / 黑名单 / 参数规则
2. **在 `tests/test_policy.py` 里加一条对应的拦截测试**
3. 在本文档里补充说明

第 2 步不可省略——**没有测试覆盖的约束等于没有约束**。

## 已知的局限

诚实地列在这里，欢迎补充：

1. **无法识别「界面里的终端」**：如果用户在 IDE 内置终端里操作，窗口标题可能不带终端特征
2. **无法阻止「用界面打开记事本写代码，再复制到终端」**：这是两步界面操作，规则层面无法区分
3. **远程桌面 / 虚拟机场景**：约束作用在被控端，宿主机不受限
4. **OCR 类绕过**：理论上可以把文件内容「看」出来（但这仍是界面操作，符合规则）

如果你发现了新的绕过方式，请提 `[BYPASS]` issue。
