# GUI-Only Agent

> **An AI that can only use its hands — never the back door.**

A constraint-enforced agent framework: the AI must complete tasks by **actually operating the graphical interface** — opening applications, clicking buttons, typing on the keyboard, hitting save — and is **forbidden** from calling file-write APIs, shell commands, HTTP requests, or any other shortcut.

---

## Why this exists

Most "AI operates your computer" projects let the agent **quietly take shortcuts**:

```
User:  Write an article and save it to the Desktop
Agent: (internally) Write a file? I'll just write_file("Desktop/article.docx") — done in one second ✓
```

The task does get done — but the **"GUI operation ability" you wanted to verify was never actually exercised**.

This project solves exactly that problem: **seal off every shortcut, leaving interface operation as the only path.**

## Core design: three locks

| Lock | Mechanism | What it prevents |
|---|---|---|
| **① Narrow tool surface** | The agent's visible tools are **GUI primitives only** (screenshot / click / type / hotkey / scroll). File and command tools are **never registered** | The model has nothing to call, even if it wants to |
| **② Policy gateway** | Every action must pass `Guard` validation before execution; non-allowlisted actions are **rejected outright and written to the violation log** | Even a hallucinated `write_file` gets blocked |
| **③ Evidence chain + GUI verification** | Screenshots are captured throughout; task verification **must also be done through the interface** (open the file and look at it), never by reading the disk | The result cannot be faked after the fact |

## The loop

```
        ┌───────────────────────────────────────────────────────────┐
        │                                                           │
  ① Observe ▼       ② Decide        ③ Validate       ④ Act       ⑤ Verify
  screenshot /  →  LLM proposes  →  Guard allow-  →  Driver   →  look at the
  a11y tree        next action       list check       really acts  screen again
        │                                                           │
        └──────── ⑥ Screenshots + action trace recorded throughout ←┘
```

## Quick start

```bash
# 1. Install
pip install -e .

# 2. Configure (see .env.example)
cp .env.example .env

# 3. Run the "write an article in Word" task
gui-only-agent run --task write_article \
  --title "Why GUI-Only Constraints Matter" \
  --body "..." \
  --save-to "$HOME/Desktop"
```

## Project structure

```
gui-only-agent/
├── src/gui_only_agent/
│   ├── policy/        # ★ Enforcement layer: allowlist, denylist, violation detection
│   ├── driver/        # Execution layer: drives the real desktop over MCP
│   ├── harness/       # Decision layer: observe-decide-act loop
│   ├── evidence/      # Evidence layer: screenshots, action trace, reports
│   ├── tasks/         # Task definitions
│   ├── model/         # LLM providers
│   └── cli.py         # Command-line entry point
├── docs/              # Architecture and policy documentation
├── examples/          # Runnable examples
├── tests/             # Tests
└── .github/workflows/ # CI
```

## Supported desktop drivers

The framework connects to desktop drivers over the **MCP protocol**, so they are swappable:

| Driver | Platform | Notes |
|---|---|---|
| [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) | Windows | Recommended, 20 tools |
| [Cua Driver](https://github.com/trycua/cua) | Win/Mac/Linux | Supports background delivery |
| [computer-use-linux](https://github.com/agent-sh/computer-use-linux) | Linux | Wayland-friendly |
| [agent-desktop](https://github.com/lahfir/agent-desktop) | macOS | Semantic accessibility-tree operation |
| `mock` | Any | Built in, used for testing |

**The goal of this project is not to be convenient — it is to be trustworthy.**

## License

MIT
