"""项目级作用域：把「只准操作界面」的约束绑定到一个文件夹。"""

from .scope import ProjectScope, ScopeNotFound

__all__ = ["ProjectScope", "ScopeNotFound"]
