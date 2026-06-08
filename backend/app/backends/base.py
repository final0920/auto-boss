"""ControlBackend 抽象基类 — observe / locate / act 统一接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass
class Coord:
    """设备像素坐标。"""
    x: int
    y: int


@dataclass
class UINode:
    """控件树中的单个节点（uia2 dump 对应字段）。"""
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    class_name: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)  # (left, top, right, bottom)
    clickable: bool = False
    enabled: bool = True
    package: str = ""
    # 原始节点对象（uiautomator2 UiObject），None 表示由视觉后端合成
    raw: Any = field(default=None, repr=False)

    @property
    def center(self) -> Coord:
        left, top, right, bottom = self.bounds
        return Coord((left + right) // 2, (top + bottom) // 2)


@dataclass
class PageState:
    """observe() 返回的页面快照。

    至少包含前台包名；nodes 为控件树节点列表（视觉后端可为空）。
    screenshot 仅视觉后端填充（PIL bytes），避免控件树路径浪费内存。
    """
    package: str = ""
    activity: str = ""
    nodes: list[UINode] = field(default_factory=list)
    screenshot_png: Optional[bytes] = None  # 仅 vision_backend 填充
    backend_name: str = ""


@dataclass
class Action:
    """act() 的输入描述。"""
    kind: str           # "tap" | "swipe" | "text" | "keyevent" | "back" | "home"
    x: int = 0
    y: int = 0
    x2: int = 0
    y2: int = 0
    duration_ms: int = 300
    text: str = ""
    keycode: int | str = 0


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class ControlBackend(ABC):
    """所有设备控制后端必须实现的统一接口。

    - observe()  : 获取当前页面状态快照
    - locate()   : 在当前页面中定位目标，返回像素坐标（失败返回 None）
    - act()      : 执行动作（tap/swipe/text/keyevent 等）

    后端切换以页面/动作为原子边界：禁止在单次 act() 执行中途切换后端。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """后端标识，如 'uia' 或 'vision'。"""

    @abstractmethod
    def observe(self) -> PageState:
        """抓取当前页面状态。

        uia_backend: dump 控件树 + get_foreground
        vision_backend: screencap → PageState(screenshot_png=...)
        """

    @abstractmethod
    def locate(self, target: str) -> Optional[Coord]:
        """在当前页面中定位目标控件/区域，返回中心像素坐标。

        target: 自然语言描述，如 "立即沟通按钮" 或 "聊天输入框"
        返回 None 表示未找到。
        """

    @abstractmethod
    def act(self, action: Action) -> None:
        """执行一个原子动作。

        写操作调用方需在 device_mode_manager.auto_write_ctx() 内调用此方法。
        """

    # ------------------------------------------------------------------
    # 便捷方法（默认实现，子类可覆盖）
    # ------------------------------------------------------------------

    def tap(self, x: int, y: int) -> None:
        self.act(Action(kind="tap", x=x, y=y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.act(Action(kind="swipe", x=x1, y=y1, x2=x2, y2=y2, duration_ms=duration_ms))

    def send_text(self, text: str) -> None:
        self.act(Action(kind="text", text=text))

    def press_back(self) -> None:
        self.act(Action(kind="back"))

    def press_home(self) -> None:
        self.act(Action(kind="home"))
