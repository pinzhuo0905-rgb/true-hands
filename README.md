# TrueHands

[![CI](https://github.com/pinzhuo0905-rgb/true-hands/actions/workflows/ci.yml/badge.svg)](https://github.com/pinzhuo0905-rgb/true-hands/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> **An AI that really operates the computer — and can prove it.**

*True hands*: it genuinely works the interface — opening applications, clicking buttons, typing on the keyboard, hitting save — rather than quietly reaching for a file API, a shell command, or an HTTP request. And because every step is screenshotted and the result is verified **through the UI**, you can prove it did.

It ships with a **built-in desktop driver** (Windows, zero third-party dependencies), so it works out of the box — no external MCP server required. The constraint is declared **per project folder**, so one directory can be strict while another is not.

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

## Project scope: the constraint follows the folder

The constraint is not a global switch — it is declared **inside the project itself**, so one folder can be strict while another is not.

Drop a `.true-hands.json` at the root of a folder, and **every task started anywhere under it** inherits that policy. In practice: *inside this project, the agent may only work by directly operating the computer.*

```bash
# Turn the current folder into a GUI-only project
true-hands project init

# See which project scope the current directory falls under
true-hands project status
```

```json
{
  "enforce": true,
  "mode": "gui-only",
  "max_steps": 60,
  "require_gui_verification": true,
  "allowed_tools": [],
  "denied_tools": [],
  "note": "Inside this project the agent may only operate the computer directly."
}
```

| Field | Meaning |
|---|---|
| `enforce` | `true` blocks violations; `false` downgrades to audit-only |
| `mode` | `gui-only` (strict) · `efficient` (allow shell) · `audit` (log only) |
| `max_steps` | Step budget for this project |
| `require_gui_verification` | Verification must also be done through the interface |
| `allowed_tools` / `denied_tools` | Project-specific additions to the allow / deny lists |

Discovery walks **up** from the current directory and stops at the nearest config, so nested projects work correctly.

## Built-in desktop driver

`--driver native` runs the bundled driver, implemented with `ctypes` calls straight into the Win32 API. **No third-party packages, no external process.**

| Capability | How |
|---|---|
| Screenshot | Pillow if installed, otherwise GDI `BitBlt` + hand-written BMP — the zero-dependency path |
| Mouse | `SendInput` (move / click / right-click / drag / scroll) |
| Keyboard | `SendInput` with `KEYEVENTF_UNICODE`, so Chinese and other non-ASCII text work |
| Hotkeys | Named keys resolved to virtual-key codes (`ctrl+s`, `alt+tab`, `win+r`, …) |
| Windows | `GetForegroundWindow` / `GetWindowTextW` for the active window title |

## Quick start

```bash
# 1. Install
pip install -e .

# 2. Configure (see .env.example)
cp .env.example .env

# 3. Run the "write an article in Word" task, using the built-in driver
true-hands run --task write_article \
  --title "Why GUI-Only Constraints Matter" \
  --body "..." \
  --driver native
```

Dry-run without touching the real desktop:

```bash
true-hands run --task write_article --driver mock
```

## Project structure

```
true-hands/
├── src/true_hands/
│   ├── policy/        # ★ Enforcement layer: allowlist, denylist, violation detection
│   ├── project/       # ★ Project scope: .true-hands.json discovery and application
│   ├── driver/        # Execution layer: native (Win32) / MCP / mock drivers
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

The framework talks to drivers through a small protocol, so they are swappable:

| Driver | Platform | Notes |
|---|---|---|
| `native` | Windows | **Built in.** `ctypes` into Win32, zero dependencies |
| `mcp` + [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) | Windows | External MCP server, 20 tools |
| `mcp` + [Cua Driver](https://github.com/trycua/cua) | Win/Mac/Linux | Supports background delivery |
| `mcp` + [computer-use-linux](https://github.com/agent-sh/computer-use-linux) | Linux | Wayland-friendly |
| `mcp` + [agent-desktop](https://github.com/lahfir/agent-desktop) | macOS | Semantic accessibility-tree operation |
| `mock` | Any | Built in, used for testing and CI |

## Verifying it works

A zero-dependency self-check exercises the whole constraint layer — no pytest required:

```bash
PYTHONPATH=src python scripts/selfcheck.py
```

It covers the rule tables, the gateway's blocking behaviour, the decision loop, and project-scope discovery.

**The goal of this project is not to be convenient — it is to be trustworthy.**

## License

MIT
