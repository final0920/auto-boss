"""VisionBackend — gpt-5.5 多模态视觉兜底后端。

流程：
  observe()  : screencap → PageState(screenshot_png=...)
  locate()   : screenshot → gpt-5.5 多模态 → 0-1000 归一化坐标 → 像素换算
  act()      : 同 UiaBackend（走 AdbDevice 非特权命令）

坐标契约（对齐 AutoGLM）：
  - LLM 返回 {"x": 0-1000, "y": 0-1000}，归一化到屏幕尺寸
  - 像素 = coord / 1000 * screen_width/height（clamp 到 [0, max]）

VLM 调用计入 RateLimiter（hook：pipeline/rate_limiter.py T5 提供，先留接口）。
device_mode 写锁由调用方持有，backend 本身不持锁。
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from app.backends.base import Action, ControlBackend, Coord, PageState
from app.adb.device import AdbDevice
from app.adb.appinfo import get_foreground_package, get_foreground_activity
from app.adb.screencap import screencap_png_bytes
from app.adb.inputs import ADBKeyboard
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RateLimiter hook（T5 提供真实实现，此处 stub 以解耦）
# ---------------------------------------------------------------------------

def _check_vlm_budget(source: str = "vision") -> bool:
    """VLM 预算检查 hook（T5 rate_limiter 实现后替换此 stub）。

    返回 True 表示有余额可用；False 表示已超额，应降级或跳过。
    """
    try:
        from app.pipeline.rate_limiter import rate_limiter
        return rate_limiter.check_and_consume_vlm(source)
    except ImportError:
        # T5 未完成时 stub 始终允许
        return True


# ---------------------------------------------------------------------------
# LLM locate hook（T12 llm/client.py 提供真实实现）
# ---------------------------------------------------------------------------

def _llm_locate(screenshot_b64: str, target: str, screen_w: int, screen_h: int) -> Optional[Coord]:
    """调用 gpt-5.5 多模态定位目标，返回像素坐标。

    先尝试 llm/client.py 的 locate 接口；未就绪时使用内联实现。
    """
    try:
        from app.llm.client import llm_client
        return llm_client.locate(screenshot_b64, target, screen_w, screen_h)
    except (ImportError, AttributeError):
        pass

    # 内联实现（T12 未完成时兜底）
    return _inline_llm_locate(screenshot_b64, target, screen_w, screen_h)


def _inline_llm_locate(
    screenshot_b64: str,
    target: str,
    screen_w: int,
    screen_h: int,
) -> Optional[Coord]:
    """直接调用 OpenAI 兼容 API 进行多模态定位。"""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 未安装，vision_backend locate 不可用")
        return None

    client = OpenAI(
        api_key=settings.gpt_api_key,
        base_url=settings.gpt_base_url,
    )

    prompt = (
        f"图片是安卓设备截图（{screen_w}x{screen_h} 像素）。"
        f'请找到目标："{target}"，'
        '返回其中心点在 0-1000 归一化坐标系中的位置，格式：{"x": <0-1000>, "y": <0-1000>}。'
        '若未找到返回 {"x": -1, "y": -1}。只输出 JSON，不要任何解释。'
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    extra_kwargs: dict = {}
    if settings.gpt_reasoning:
        extra_kwargs["reasoning_effort"] = settings.gpt_reasoning

    try:
        resp = client.chat.completions.create(
            model=settings.gpt_model,
            messages=messages,
            max_tokens=64,
            **extra_kwargs,
        )
    except Exception as exc:
        logger.error("VisionBackend LLM 调用失败: %s", exc)
        return None

    raw = resp.choices[0].message.content or ""
    return _parse_norm_coord(raw, screen_w, screen_h)


def _parse_norm_coord(raw: str, screen_w: int, screen_h: int) -> Optional[Coord]:
    """解析 LLM 返回的 0-1000 归一化坐标，换算为像素。"""
    import json
    import re

    # 尝试提取 JSON 对象
    m = re.search(r'\{[^}]+\}', raw)
    if not m:
        logger.warning("VisionBackend 解析 LLM 坐标失败，原始输出: %r", raw[:200])
        return None

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        logger.warning("VisionBackend JSON 解析失败: %r", m.group())
        return None

    nx = data.get("x", -1)
    ny = data.get("y", -1)

    if nx < 0 or ny < 0:
        # LLM 返回 -1 表示未找到
        return None

    # clamp 到 [0, 1000]，再换算像素
    nx = max(0, min(1000, float(nx)))
    ny = max(0, min(1000, float(ny)))

    px = int(nx / 1000 * screen_w)
    py = int(ny / 1000 * screen_h)

    # 边界 clamp
    px = max(0, min(screen_w - 1, px))
    py = max(0, min(screen_h - 1, py))

    return Coord(x=px, y=py)


# ---------------------------------------------------------------------------
# VisionBackend
# ---------------------------------------------------------------------------


class VisionBackend(ControlBackend):
    """gpt-5.5 多模态视觉兜底后端。"""

    def __init__(self, serial: str):
        self.serial = serial
        self._adb = AdbDevice(serial)
        self._screen_size: Optional[tuple[int, int]] = None  # (width, height)
        self._last_screenshot_png: Optional[bytes] = None

    @property
    def name(self) -> str:
        return "vision"

    # ------------------------------------------------------------------
    # 屏幕尺寸（懒加载 + 缓存）
    # ------------------------------------------------------------------

    def _get_screen_size(self) -> tuple[int, int]:
        if self._screen_size:
            return self._screen_size
        result = self._adb.dumpsys("window displays")
        import re
        m = re.search(r'cur=(\d+)x(\d+)', result.stdout)
        if m:
            self._screen_size = (int(m.group(1)), int(m.group(2)))
        else:
            # 回退：从截图推断
            png = screencap_png_bytes(self.serial)
            from PIL import Image
            from io import BytesIO
            img = Image.open(BytesIO(png))
            self._screen_size = img.size  # (width, height)
        return self._screen_size

    # ------------------------------------------------------------------
    # observe
    # ------------------------------------------------------------------

    def observe(self) -> PageState:
        pkg = get_foreground_package(self.serial) or ""
        act = get_foreground_activity(self.serial) or ""
        png = screencap_png_bytes(self.serial)
        self._last_screenshot_png = png
        return PageState(
            package=pkg,
            activity=act,
            nodes=[],           # vision 后端不提供控件树
            screenshot_png=png,
            backend_name=self.name,
        )

    # ------------------------------------------------------------------
    # locate
    # ------------------------------------------------------------------

    def locate(self, target: str) -> Optional[Coord]:
        """截图 → gpt-5.5 多模态 → 0-1000 归一化坐标 → 像素坐标。"""
        # VLM 预算检查（hook）
        if not _check_vlm_budget("vision"):
            logger.warning("VisionBackend locate '%s' 被 RateLimiter 熔断，跳过", target)
            return None

        # 复用已有截图（observe 后 locate 无需重截）或重新截图
        png = self._last_screenshot_png
        if png is None:
            png = screencap_png_bytes(self.serial)
            self._last_screenshot_png = png

        screenshot_b64 = base64.b64encode(png).decode("ascii")
        screen_w, screen_h = self._get_screen_size()

        logger.debug("VisionBackend locate '%s' screen=%dx%d", target, screen_w, screen_h)
        coord = _llm_locate(screenshot_b64, target, screen_w, screen_h)

        if coord is None:
            logger.info("VisionBackend locate '%s' 未命中", target)
        else:
            logger.debug("VisionBackend locate '%s' → (%d, %d)", target, coord.x, coord.y)

        # 使用后清空，下次 locate 前必须重新 observe 或截图
        self._last_screenshot_png = None
        return coord

    # ------------------------------------------------------------------
    # act — 与 UiaBackend 一致，走 AdbDevice 非特权命令
    # ------------------------------------------------------------------

    def act(self, action: Action) -> None:
        dev = self._adb
        match action.kind:
            case "tap":
                dev.humanized_tap(action.x, action.y)
            case "swipe":
                dev.humanized_swipe(
                    action.x, action.y, action.x2, action.y2,
                    step_delay_ms=30,
                )
            case "text":
                with ADBKeyboard(self.serial) as kb:
                    kb.send_text(action.text)
            case "keyevent":
                dev.keyevent(action.keycode)
            case "back":
                dev.press_back()
            case "home":
                dev.press_home()
            case _:
                raise ValueError(f"未知 action.kind: {action.kind!r}")
