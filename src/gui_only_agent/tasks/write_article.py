"""示例任务：用文字处理软件写一篇文章并保存。

这个任务是本项目的「样板间」——它刻意设计成**只有走界面才可能完成**：

* 不能 write_file，因为文件工具压根不在工具表里
* 不能 echo 重定向，因为没有 Shell
* 只能：打开 Word → 在编辑区打字 → Ctrl+S → 在弹窗里选路径 → 点保存 → 再打开确认

验收同样走界面：去桌面看一眼文件在不在，双击打开确认内容。
"""

from __future__ import annotations

from .base import Task


def build_write_article(title: str, body: str, save_to: str = "桌面") -> Task:
    """构造一个「写文章并保存」的任务。"""
    return Task(
        name="write_article",
        goal=(
            f"使用文字处理软件（如 Microsoft Word 或 WPS）撰写一篇文章。\n"
            f"文章标题：{title}\n"
            f"文章正文：{body}\n"
            f"写完后保存到「{save_to}」，文件名使用文章标题。"
        ),
        app_hint="Microsoft Word（若未安装则用记事本 / WPS 替代）",
        success_criteria=(
            f"「{save_to}」下存在一个以「{title}」命名的文档文件，"
            f"用软件打开后内容与要求一致。"
        ),
        verify_prompt=(
            "现在做最后验收，全部用界面操作完成：\n"
            f"1. 打开文件资源管理器，进入「{save_to}」\n"
            f"2. 在文件列表里找到以文章标题命名的文件\n"
            "3. 双击打开它\n"
            "4. 截图确认内容与要求一致\n"
            "5. 如果一致输出 {\"done\": true}，否则输出下一步修正动作"
        ),
        metadata={"title": title, "body": body, "save_to": save_to},
    )


WRITE_ARTICLE = build_write_article(
    title="论界面操作的必要性",
    body=(
        "当 AI 可以直接调用文件接口时，我们无法确认它是否真的理解了软件界面。\n"
        "强制它打开软件、在界面里输入、点击保存，才能验证真实的界面操作能力。\n"
        "这不是效率问题，而是可信度问题。"
    ),
)
