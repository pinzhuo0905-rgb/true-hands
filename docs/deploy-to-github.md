# 部署到 GitHub

从零到上线，一共 6 步。前 3 步在本地完成，后 3 步推上 GitHub。

## 一、仓库结构

```
gui-only-agent/
├── README.md                      # 门面：为什么做、怎么做、怎么用
├── LICENSE                        # MIT
├── CONTRIBUTING.md                # 贡献指南（强调"改约束需论证"）
├── .gitignore                     # 排除 .venv / runs / .env
├── .env.example                   # 配置模板（不含真实密钥）
├── pyproject.toml                 # 打包 + 依赖 + 工具配置
│
├── src/gui_only_agent/            # 源码（src 布局，避免导入歧义）
│   ├── __init__.py
│   ├── cli.py                     # 命令行入口
│   ├── policy/                    # ★ 强制约束层
│   │   ├── __init__.py
│   │   ├── rules.py               # 规则表（白/黑名单、参数校验）
│   │   └── guard.py               # 网关：校验 + 记录违规
│   ├── driver/                    # 执行层
│   │   ├── __init__.py
│   │   ├── base.py                # Driver 协议
│   │   ├── mcp_client.py          # MCP stdio 客户端
│   │   └── mock.py                # 测试用假驱动
│   ├── harness/                   # 决策层
│   │   ├── __init__.py
│   │   ├── loop.py                # 观察-决策-校验-执行循环
│   │   └── verifier.py            # 界面验收器
│   ├── evidence/                  # 证据层
│   │   ├── __init__.py
│   │   └── recorder.py            # 截图 + 轨迹 + 报告
│   ├── model/                     # 模型层
│   │   ├── __init__.py
│   │   └── provider.py            # OpenAI 兼容提供方
│   └── tasks/                     # 任务定义
│       ├── __init__.py
│       ├── base.py                # Task 数据结构
│       └── write_article.py       # 示例任务
│
├── tests/
│   ├── test_policy.py             # ★ 最重要：约束是否真的拦得住
│   └── test_loop.py               # 循环与"拒绝回灌"行为
│
├── docs/
│   ├── architecture.md            # 架构与设计决策
│   ├── policy.md                  # 约束规范（自然语言版规则）
│   └── deploy-to-github.md        # 本文
│
├── examples/
│   └── write-article-word/
│       └── README.md              # 端到端示例说明
│
└── .github/
    └── workflows/
        └── ci.yml                 # CI：测试 + 风格 + 规则自洽校验
```

## 二、必备配置文件说明

| 文件 | 作用 | 要点 |
|---|---|---|
| `pyproject.toml` | 打包与依赖 | `requires-python >=3.10`；`[project.scripts]` 定义 `gui-only-agent` 命令；`[tool.setuptools.packages.find] where=["src"]` 配合 src 布局 |
| `.gitignore` | 排除不该入库的东西 | **务必排除 `.env`、`.venv/`、`runs/`**（runs 里有大量截图，会把仓库撑爆） |
| `.env.example` | 配置模板 | 只放占位符，**绝不放真实密钥** |
| `LICENSE` | 开源协议 | MIT，最宽松，便于他人复用 |
| `.github/workflows/ci.yml` | 持续集成 | 跑测试 + ruff + 一条"白名单与黑名单不得重叠"的自洽断言 |
| `CONTRIBUTING.md` | 贡献指南 | 明确"任何削弱约束的改动需论证" |

### 关于密钥安全

`.env` 已在 `.gitignore` 里，但**第一次提交前请再确认一次**：

```bash
git status --ignored | grep -E "\.env$"   # 应该能看到 .env 被忽略
```

一旦密钥进了 Git 历史，删文件是没用的——必须用 `git filter-repo` 重写历史，
或者直接吊销密钥。**所以宁可多检查一遍。**

## 三、本地初始化

```bash
cd gui-only-agent

# 1. 初始化仓库
git init -b main

# 2. 确认忽略规则生效（关键一步）
git status --short          # 不应出现 .venv/ 和 .env

# 3. 首次提交
git add .
git commit -m "feat: 初始化 gui-only-agent

强制 AI 只能通过真实操作图形界面完成任务。

核心设计：
- policy/ 策略网关：白名单 + 黑名单 + 参数级校验
- 默认拒绝原则：不在白名单的动作一律不执行
- 拒绝理由回灌模型，连续 3 次偷懒则中止
- 验收也必须走界面，无法通过读磁盘伪造结果"

# 4. 跑一遍测试，确保推上去的是绿的
pytest -q
```

## 四、推到 GitHub

### 方式 A：用 GitHub CLI（推荐，一步到位）

```bash
gh auth login                 # 首次需要
gh repo create gui-only-agent --public --source=. --remote=origin --push
```

### 方式 B：手动创建

```bash
# 先在网页上建一个空仓库（不要勾选 README / .gitignore / LICENSE）
git remote add origin https://github.com/<你的用户名>/gui-only-agent.git
git push -u origin main
```

## 五、推上去之后

1. **加仓库话题标签**，方便被搜到：
   `ai-agent` `gui-automation` `computer-use` `mcp` `evaluation` `llm`

2. **确认 CI 跑通**：Actions 页应该出现绿色的 ✅

3. **补充仓库描述**（一句话）：
   > 强制 AI 只能通过真实操作图形界面完成任务的 Agent 框架

4. **打第一个 tag**：
   ```bash
   git tag -a v0.1.0 -m "首个可用版本"
   git push origin v0.1.0
   ```

## 六、后续维护建议

| 事项 | 建议 |
|---|---|
| 分支策略 | `main` 保护，改动走 PR |
| 版本号 | 语义化版本；改约束规则 → minor；改架构 → major |
| 新增绕过路径 | 开 `[BYPASS]` issue，最高优先级 |
| 规则变更 | PR 必须附带测试，否则不予合并 |
| 证据目录 | `runs/` 不入库；如需分享结果，单独打包压缩包放 Releases |

## 可选：发布到 PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

发布后别人就能 `pip install gui-only-agent` 直接用。
