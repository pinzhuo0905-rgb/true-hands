# 示例：用 Word 写一篇文章

这是本项目最具代表性的示例——**它只能靠界面操作完成**。

## 目标

```
使用文字处理软件（如 Microsoft Word 或 WPS）撰写一篇文章。
文章标题：论界面操作的必要性
文章正文：……
写完后保存到「桌面」，文件名使用文章标题。
```

## 为什么这个例子有说服力

因为**所有捷径都被堵死了**：

| 捷径 | 为什么走不通 |
|---|---|
| `write_file("桌面/文章.docx")` | 文件工具不在白名单 |
| `echo "..." > 文章.txt` | 没有 Shell |
| 调 Word 的 COM 接口 | 没有这个工具 |
| 生成 docx 字节流 | 没有文件写入能力 |

**只剩一条路**：打开 Word → 在编辑区打字 → Ctrl+S → 在弹窗里选桌面 → 点保存。

## 预期动作序列

```
 0  Snapshot    看当前屏幕
 1  App         启动 Word
 2  Wait        等 Word 加载
 3  Snapshot    确认已打开、找到编辑区
 4  Click       点进编辑区
 5  Type        输入标题
 6  Shortcut    Enter 换行
 7  Type        输入正文
 8  Shortcut    Ctrl+S
 9  Wait        等"另存为"弹窗
10  Snapshot    看弹窗
11  Click       点左侧「桌面」
12  Type        输入文件名
13  Click       点「保存」
14  Snapshot    确认保存成功
```

然后**验收**（同样是界面操作）：

```
15  App         打开文件资源管理器
16  Snapshot    看桌面有没有这个文件
17  Click       双击打开
18  Snapshot    确认内容正确
19  → done
```

## 运行

```bash
# 空跑（mock 驱动，不碰真实桌面）
gui-only-agent run --task write_article --dry-run

# 真实执行
gui-only-agent run --task write_article \
  --title "论界面操作的必要性" \
  --body "当 AI 可以直接调用文件接口时，我们无法确认它是否真的理解了软件界面。" \
  --driver-command "C:\Users\<你>\.local\bin\windows-mcp.exe" \
  --driver-arg serve
```

## 看结果

运行结束后，`runs/<run-id>/` 下会有：

- `run.json` —— 结论 + 策略报告（违规了几次、分别是什么）
- `trace.jsonl` —— 每一步的动作与前后截图路径
- `shots/` —— 所有截图

**打开 `shots/` 逐张看，就能确认它是不是真的一步步在界面上操作。**
