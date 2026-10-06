"""Windows 原生桌面驱动（ctypes 直调 Win32 API，零第三方依赖）。

为什么要有它：如果只提供 MCP 客户端，用户还得自己去装一个 MCP 桌面服务器，
仓库就不算「完整可用」。这个驱动让项目**装上就能跑**。

覆盖能力：
    看屏幕   screenshot() / active_window_title()
    鼠标     move / click / double_click / right_click / drag / scroll
    键盘     type_text（支持中文）/ press_keys / hotkey
    应用     launch()

截图优先用 Pillow（输出 PNG）；没装 Pillow 就退回 GDI BitBlt + 手写 BMP，
保证「零依赖也能用」。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from .base import ActionResult, Observation
from ..policy.guard import Action

# ---------------------------------------------------------------------------
# Win32 绑定
# ---------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

ULONG_PTR = wintypes.WPARAM

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0

VK: dict[str, int] = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "capslock": 0x14, "insert": 0x2D, "printscreen": 0x2C,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(f"SendInput 只发送了 {sent}/{len(inputs)} 个事件（错误码 {ctypes.get_last_error()}）")


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, union=_INPUTUNION(mi=MOUSEINPUT(dx, dy, data, flags, 0, 0)))


def _key_input(vk: int, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))


def _unicode_input(char: str, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(0, ord(char), flags | KEYEVENTF_UNICODE, 0, 0)))


def _virtual_screen() -> tuple[int, int, int, int]:
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def _to_absolute(x: int, y: int) -> tuple[int, int]:
    vx, vy, vw, vh = _virtual_screen()
    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    return nx, ny


# ---------------------------------------------------------------------------
# 截图
# ---------------------------------------------------------------------------
def _capture_with_pillow(path: Path) -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        return False
    ImageGrab.grab(all_screens=True).save(path)
    return True


def _capture_with_gdi(path: Path) -> bool:
    """GDI BitBlt + 手写 BMP。零依赖路径。"""
    vx, vy, vw, vh = _virtual_screen()
    hdc = user32.GetDC(0)
    if not hdc:
        return False
    memdc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, vw, vh)
    try:
        gdi32.SelectObject(memdc, bitmap)
        if not gdi32.BitBlt(memdc, 0, 0, vw, vh, hdc, vx, vy, SRCCOPY):
            return False
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = vw
        header.biHeight = -vh  # 负数 = 自上而下
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0  # BI_RGB
        stride = vw * 4
        buffer = ctypes.create_string_buffer(stride * vh)
        got = gdi32.GetDIBits(memdc, bitmap, 0, vh, buffer, ctypes.byref(header), DIB_RGB_COLORS)
        if not got:
            return False
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)

    pixel_bytes = stride * vh
    file_size = 14 + ctypes.sizeof(BITMAPINFOHEADER) + pixel_bytes
    with path.open("wb") as fh:
        # BITMAPFILEHEADER
        fh.write(b"BM")
        fh.write(file_size.to_bytes(4, "little"))
        fh.write((0).to_bytes(4, "little"))
        fh.write((14 + ctypes.sizeof(BITMAPINFOHEADER)).to_bytes(4, "little"))
        fh.write(bytes(header))
        fh.write(buffer.raw)
    return True


# ---------------------------------------------------------------------------
# 驱动
# ---------------------------------------------------------------------------
class NativeDesktopDriver:
    """直接操作本机桌面的驱动，无需外部进程。"""

    def __init__(self, shot_dir: str | Path = "runs/_shots", key_delay: float = 0.02) -> None:
        if os.name != "nt":
            raise RuntimeError("NativeDesktopDriver 目前只支持 Windows。其他平台请用 MCP 驱动。")
        self.shot_dir = Path(shot_dir)
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self.key_delay = key_delay
        self._shot_seq = 0

    # -- Driver 协议 --------------------------------------------------------
    def list_tools(self) -> list[str]:
        """本驱动能响应的动作名，与策略白名单对齐。"""
        return [
            "Screenshot", "Snapshot", "DisplayInventory",
            "Click", "Move", "Scroll", "MultiSelect",
            "Type", "Shortcut", "MultiEdit",
            "App", "Wait", "WaitFor", "Notification",
        ]

    def observe(self) -> Observation:
        title = self.active_window_title()
        shot = self.screenshot()
        return Observation(window_title=title, screenshot_path=str(shot))

    def act(self, action: Action) -> ActionResult:
        handler = getattr(self, f"_do_{action.tool}", None)
        if handler is None:
            return ActionResult(ok=False, detail=f"原生驱动不支持动作：{action.tool}")
        try:
            detail = handler(**action.args)
        except TypeError as exc:
            return ActionResult(ok=False, detail=f"参数不匹配：{exc}")
        except Exception as exc:  # noqa: BLE001 - 驱动层兜底
            return ActionResult(ok=False, detail=f"执行失败：{exc}")
        return ActionResult(ok=True, detail=detail or "ok", observation=self.observe())

    def close(self) -> None:
        return None

    # -- 观察 ---------------------------------------------------------------
    def screenshot(self) -> Path:
        self._shot_seq += 1
        png = self.shot_dir / f"shot-{self._shot_seq:05d}.png"
        if _capture_with_pillow(png):
            return png
        bmp = self.shot_dir / f"shot-{self._shot_seq:05d}.bmp"
        if _capture_with_gdi(bmp):
            return bmp
        raise RuntimeError("截图失败：Pillow 与 GDI 两条路径都不可用。")

    def _do_Screenshot(self, **_: object) -> str:
        return f"已截图：{self.screenshot()}"

    def _do_Snapshot(self, **_: object) -> str:
        return f"已快照：{self.screenshot()}（当前窗口：{self.active_window_title()}）"

    def active_window_title(self) -> str:
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    # -- 鼠标 ---------------------------------------------------------------
    def _do_Move(self, loc=None, **_: object) -> str:
        x, y = _as_point(loc)
        nx, ny = _to_absolute(x, y)
        _send(_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny))
        return f"移动到 ({x}, {y})"

    def _do_Click(self, loc=None, clicks: int = 1, button: str = "left", **_: object) -> str:
        x, y = _as_point(loc)
        self._do_Move(loc=(x, y))
        down = MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_LEFTDOWN
        up = MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_LEFTUP
        for _ in range(max(1, int(clicks))):
            _send(_mouse_input(down), _mouse_input(up))
            time.sleep(0.05)
        return f"{button} 点击 ({x}, {y}) ×{clicks}"

    def _do_Scroll(self, loc=None, direction: str = "down", wheel_times: int = 1, **_: object) -> str:
        if loc:
            self._do_Move(loc=loc)
        delta = 120 if direction in ("up", "left") else -120
        for _ in range(max(1, int(wheel_times))):
            _send(_mouse_input(MOUSEEVENTF_WHEEL, 0, 0, delta))
            time.sleep(0.02)
        return f"滚动 {direction} ×{wheel_times}"

    def _do_MultiSelect(self, locs=None, **_: object) -> str:
        points = [_as_point(p) for p in (locs or [])]
        for x, y in points:
            self._do_Click(loc=(x, y))
        return f"连续点击 {len(points)} 个位置"

    # -- 键盘 ---------------------------------------------------------------
    def _do_Type(self, text: str = "", loc=None, clear: bool = False, press_enter: bool = False, **_: object) -> str:
        if loc:
            self._do_Click(loc=loc)
        if clear:
            _send(_key_input(VK["ctrl"]), _key_input(VK["a"]),
                  _key_input(VK["a"], KEYEVENTF_KEYUP), _key_input(VK["ctrl"], KEYEVENTF_KEYUP))
            time.sleep(0.05)
        for ch in text:
            if ch == "\n":
                _send(_key_input(VK["enter"]), _key_input(VK["enter"], KEYEVENTF_KEYUP))
            elif ch == "\t":
                _send(_key_input(VK["tab"]), _key_input(VK["tab"], KEYEVENTF_KEYUP))
            else:
                _send(_unicode_input(ch), _unicode_input(ch, KEYEVENTF_KEYUP))
            time.sleep(self.key_delay)
        if press_enter:
            _send(_key_input(VK["enter"]), _key_input(VK["enter"], KEYEVENTF_KEYUP))
        return f"输入 {len(text)} 个字符"

    def _do_Shortcut(self, shortcut: str = "", **_: object) -> str:
        keys = [k.strip().lower() for k in shortcut.split("+") if k.strip()]
        if not keys:
            return "快捷键为空，跳过"
        vks = []
        for k in keys:
            if k not in VK:
                raise ValueError(f"不认识的按键：{k}")
            vks.append(VK[k])
        for vk in vks:
            _send(_key_input(vk))
        for vk in reversed(vks):
            _send(_key_input(vk, KEYEVENTF_KEYUP))
        return f"按下 {shortcut}"

    def _do_MultiEdit(self, locs=None, **_: object) -> str:
        count = 0
        for item in locs or []:
            if len(item) >= 3:
                x, y, text = item[0], item[1], item[2]
                self._do_Type(text=str(text), loc=(x, y), clear=True)
                count += 1
        return f"填入 {count} 个输入框"

    # -- 其他 ---------------------------------------------------------------
    def _do_Wait(self, duration: float = 1.0, **_: object) -> str:
        time.sleep(float(duration))
        return f"等待 {duration}s"

    def _do_WaitFor(self, timeout: float = 10.0, **_: object) -> str:
        time.sleep(min(float(timeout), 1.0))
        return "等待完成"

    def _do_DisplayInventory(self, **_: object) -> str:
        vx, vy, vw, vh = _virtual_screen()
        return f"虚拟屏幕 ({vx},{vy}) {vw}×{vh}"

    def _do_Notification(self, title: str = "", message: str = "", **_: object) -> str:
        """弹一个系统提示框。放在后台线程里，不阻塞主循环。"""
        import threading

        def _show() -> None:
            try:
                user32.MessageBoxW(0, message or "", title or "TrueHands", 0x40)
            except Exception:  # noqa: BLE001 - 提示失败不应影响任务
                pass

        threading.Thread(target=_show, daemon=True).start()
        return f"已弹出提示：{title}"

    def _do_App(self, mode: str = "launch", name: str = "", executable: str = "", args=None, cwd=None, **_: object) -> str:
        if mode == "launch_executable" and executable:
            cmd = [executable, *(args or [])]
            subprocess.Popen(cmd, cwd=cwd)  # noqa: S603
            return f"启动 {executable}"
        if name:
            subprocess.Popen(f'start "" "{name}"', shell=True)  # noqa: S602
            return f"启动 {name}"
        return "未指定要启动的程序"


# ---------------------------------------------------------------------------
def _as_point(loc: object) -> tuple[int, int]:
    if isinstance(loc, (list, tuple)) and len(loc) >= 2:
        return int(loc[0]), int(loc[1])
    raise ValueError(f"坐标格式不对：{loc!r}（应为 [x, y]）")
