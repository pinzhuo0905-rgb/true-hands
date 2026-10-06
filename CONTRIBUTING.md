# 参与贡献

感谢你有兴趣参与！这个项目的核心价值在于**约束的严谨性**——所以对改动的审查会比一般项目更严。

## 最重要的一条

**任何削弱约束的改动都需要充分论证。**

比如：

- 往白名单里加工具 → 必须说明为什么它是「界面操作」而非「捷径」
- 往黑名单里删工具 → 基本不会被接受，除非有强证据
- 放宽参数校验 → 需要给出「为什么不会被绕过」的分析

## 开发环境

```bash
git clone https://github.com/your-name/true-hands.git
cd true-hands
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

## 提交前自检

1. `pytest -q` 全绿
2. `ruff check src tests` 无告警
3. **新增一条绕过路径时，同步新增一条拦截测试**（见 `tests/test_policy.py`）

## 提交信息规范

用约定式提交：

```
feat(policy): 拦截通过 App 启动解释器的绕过方式
fix(harness): 拒绝理由未回灌给模型导致死循环
docs(readme): 补充 macOS 驱动的配置示例
```

## 新增一个任务

在 `src/true_hands/tasks/` 下建文件，用 `Task` 描述目标与**界面验收方式**。

⚠️ 注意：`verify_prompt` 里**不能出现读文件、查数据库**这类验收方式——验收本身也必须是界面操作。

## 报告问题

如果是「发现了绕过约束的方法」，请在 issue 标题前加 `[BYPASS]`，这属于最高优先级。
