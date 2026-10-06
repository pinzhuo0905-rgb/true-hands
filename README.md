# GUI-Only Agent

> **让 AI 只能"动手"，不能"走后门"。**

一个强制约束的 Agent 框架：AI 必须通过**真实操作图形界面**来完成任务——打开软件、点按钮、敲键盘、点保存——**禁止**调用文件写入、Shell 命令、HTTP 请求等任何"捷径"。

---

## 为什么需要它

现在大多数"AI 操作电脑"的项目，Agent 其实都在**偷偷走捷径**：

```
用户：帮我写一篇文章保存到桌面
Agent：（内心）写文件？我直接 write_file("桌面/文章.docx") 一秒搞定 ✓
```

它确实完成了任务，但你**想验证的"GUI 操作能力"根本没被使用**。

这个项目解决的就是这个问题：**把捷径全部堵死，只留下界面操作这一条路。**

## 核心设计：三道锁

| 锁 | 机制 | 防的是什么 |
|---|---|---|
| **① 工具面收窄** | Agent 可见的工具**只有 GUI 原语**（截图/点击/输入/快捷键/滚动），文件与命令类工具**根本不注册** | 模型想调也无从调起 |
| **② 策略网关** | 每一个动作在执行前必须通过 `Guard` 校验；非白名单动作**直接拒绝并记入违规日志** | 模型幻觉出一个 `write_file` 也会被拦下 |
| **③ 证据链 + 界面验收** | 全程截图留痕；任务验收也**必须用界面完成**（打开文件看一眼），而非读磁盘 | 事后无法伪造成"GUI 产出" |

## 工作循环

```
       ┌──────────────────────────────────────────┐
       │                                          │
  ①观察 ▼            ②决策            ③校验           ④执行          ⑤验收
 截图/无障碍树 → LLM 提出下一步 → Guard 白名单校验 → Driver 真的点击 → 再看一眼屏幕
       │                                                          │
       └──────────────── ⑥ 全程截图 + 动作轨迹留痕 ←───────────────┘
```

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置（见 .env.example）
cp .env.example .env

# 3. 跑一个"用 Word 写文章"的任务
gui-only-agent run --task write_article \
  --title "论 GUI 强制约束的意义" \
  --body "..." \
  --save-to "$HOME/Desktop"
```

## 项目结构

```
gui-only-agent/
├── src/gui_only_agent/
│   ├── policy/        # ★ 强制约束层：白名单、黑名单、违规检测
│   ├── driver/        # 执行层：通过 MCP 协议驱动真实桌面
│   ├── harness/       # 决策层：观察-决策-执行循环
│   ├── evidence/      # 证据层：截图、动作轨迹、报告
│   ├── tasks/         # 任务定义
│   ├── model/         # LLM 提供方
│   └── cli.py         # 命令行入口
├── docs/              # 架构与策略文档
├── examples/          # 可运行示例
├── tests/             # 测试
└── .github/workflows/ # CI
```

## 支持的桌面驱动

框架通过 **MCP 协议**接入桌面驱动，因此可以换：

| 驱动 | 平台 | 说明 |
|---|---|---|
| [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) | Windows | 推荐，20 个工具 |
| [Cua Driver](https://github.com/trycua/cua) | Win/Mac/Linux | 支持后台投递 |
| [computer-use-linux](https://github.com/agent-sh/computer-use-linux) | Linux | Wayland 友好 |
| [agent-desktop](https://github.com/lahfir/agent-desktop) | macOS | 无障碍树语义操作 |
| `mock` | 任意 | 内置，用于测试 |

## 适合用来做什么

- **评测 GUI Agent 的真实能力**——排除脚本捷径后的裸能力
- **生成训练数据**——每一步都是真实界面操作，轨迹干净
- **验证"AI 能不能真的代替人用软件"**——这是很多宣称做不到的
- **教学演示**——直观展示 Agent 的界面理解与操作过程

## 不适合用来做什么

- ❌ 追求效率的日常自动化（那应该直接用脚本，快几十倍）
- ❌ 无人值守的批量任务（GUI 操作慢且脆弱）

**这个项目的目标不是"好用"，而是"可信"。**

## License

MIT
