"""UiaBackend — uiautomator2 控件树主后端，含三级降级。

三级降级判据（对齐 plan §4 / AC4）：
  1. 控件树直接命中（resourceId / text / content-desc）
  2. 关键字段命中率 < T_CTRL(0.8)：对缺字段区域做局部 OCR（rapidocr），仅裁剪缺失节点的 bounds 区域
  3. OCR 置信度 < T_OCR(0.6)：升级到 vision_backend 处理该 locate 请求

切换原子性：locate/act 以页面/动作为原子边界；
act() 内部不切换后端，由上层 BackendManager 负责切换时序。

device_mode 写锁由调用方（executor / api）持有，backend 本身不持锁。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.backends.base import Action, ControlBackend, Coord, PageState, UINode
from app.adb.device import AdbDevice
from app.adb.appinfo import get_foreground_package, get_foreground_activity
from app.adb.screencap import screencap_region
from app.adb.inputs import ADBKeyboard
from app.config import settings

logger = logging.getLogger(__name__)

# uiautomator2 按需导入
try:
    import uiautomator2 as u2
    _U2_AVAILABLE = True
except ImportError:
    _U2_AVAILABLE = False
    logger.warning("uiautomator2 未安装，UiaBackend 不可用")

# rapidocr 按需导入
try:
    from rapidocr_onnxruntime import RapidOCR
    _OCR_ENGINE: Optional[RapidOCR] = RapidOCR()
except ImportError:
    _OCR_ENGINE = None
    logger.warning("rapidocr-onnxruntime 未安装，局部 OCR 降级不可用")


# ---------------------------------------------------------------------------
# 辅助：控件树节点转 UINode
# ---------------------------------------------------------------------------

def _u2_info_to_node(info: dict) -> UINode:
    """将 uiautomator2 dump info dict 转为 UINode。"""
    bounds_raw = info.get("bounds", {})
    if isinstance(bounds_raw, dict):
        # {'left': x, 'top': y, 'right': r, 'bottom': b}
        left = bounds_raw.get("left", 0)
        top = bounds_raw.get("top", 0)
        right = bounds_raw.get("right", 0)
        bottom = bounds_raw.get("bottom", 0)
    elif isinstance(bounds_raw, (list, tuple)) and len(bounds_raw) == 4:
        left, top, right, bottom = bounds_raw
    else:
        left = top = right = bottom = 0

    return UINode(
        resource_id=info.get("resourceId") or info.get("resource-id") or "",
        text=info.get("text") or "",
        content_desc=info.get("contentDescription") or info.get("content-desc") or "",
        class_name=info.get("className") or info.get("class") or "",
        bounds=(left, top, right, bottom),
        clickable=bool(info.get("clickable", False)),
        enabled=bool(info.get("enabled", True)),
        package=info.get("package") or "",
        raw=info,
    )


# ---------------------------------------------------------------------------
# 辅助：OCR 局部区域
# ---------------------------------------------------------------------------

def _ocr_region(serial: str, bounds: tuple[int, int, int, int]) -> tuple[str, float]:
    """对 bounds 区域截图做 OCR，返回 (text, avg_confidence)。

    confidence = 0.0 表示 OCR 未安装或识别为空。
    """
    if _OCR_ENGINE is None:
        return "", 0.0
    left, top, right, bottom = bounds
    try:
        img = screencap_region(serial, left, top, right - left, bottom - top)
        import numpy as np
        result, _ = _OCR_ENGINE(np.array(img))
        if not result:
            return "", 0.0
        texts = [r[1] for r in result]
        confs = [float(r[2]) for r in result]
        return " ".join(texts), sum(confs) / len(confs)
    except Exception as exc:
        logger.debug("局部 OCR 失败 bounds=%s: %s", bounds, exc)
        return "", 0.0


# ---------------------------------------------------------------------------
# UiaBackend
# ---------------------------------------------------------------------------

class UiaBackend(ControlBackend):
    """uiautomator2 控件树主后端。"""

    def __init__(self, serial: str):
        if not _U2_AVAILABLE:
            raise RuntimeError("uiautomator2 未安装，无法创建 UiaBackend")
        self.serial = serial
        self._dev: u2.Device = u2.connect(serial)
        self._adb = AdbDevice(serial)
        self._last_nodes: list[UINode] = []

    @property
    def name(self) -> str:
        return "uia"

    # ------------------------------------------------------------------
    # observe
    # ------------------------------------------------------------------

    def observe(self) -> PageState:
        """dump 控件树，返回 PageState。"""
        pkg = get_foreground_package(self.serial) or ""
        act = get_foreground_activity(self.serial) or ""

        try:
            dump = self._dev.dump_hierarchy()
            nodes = self._parse_dump(dump)
        except Exception as exc:
            logger.warning("uia dump_hierarchy 失败: %s", exc)
            nodes = []

        self._last_nodes = nodes
        return PageState(
            package=pkg,
            activity=act,
            nodes=nodes,
            backend_name=self.name,
        )

    def _parse_dump(self, dump: str) -> list[UINode]:
        """将 XML dump 解析为 UINode 列表（简化版，基于属性提取）。"""
        nodes: list[UINode] = []
        # uiautomator2 dump 返回 XML 字符串，直接用 re 提取节点属性
        pattern = re.compile(
            r'<node[^>]+resource-id="(?P<rid>[^"]*)"[^>]*'
            r'text="(?P<text>[^"]*)"[^>]*'
            r'content-desc="(?P<desc>[^"]*)"[^>]*'
            r'class="(?P<cls>[^"]*)"[^>]*'
            r'package="(?P<pkg>[^"]*)"[^>]*'
            r'clickable="(?P<click>[^"]*)"[^>]*'
            r'enabled="(?P<enabled>[^"]*)"[^>]*'
            r'bounds="\[(?P<l>\d+),(?P<t>\d+)\]\[(?P<r>\d+),(?P<b>\d+)\]"',
        )
        for m in pattern.finditer(dump):
            nodes.append(UINode(
                resource_id=m.group("rid"),
                text=m.group("text"),
                content_desc=m.group("desc"),
                class_name=m.group("cls"),
                package=m.group("pkg"),
                clickable=m.group("click") == "true",
                enabled=m.group("enabled") == "true",
                bounds=(int(m.group("l")), int(m.group("t")),
                        int(m.group("r")), int(m.group("b"))),
            ))
        return nodes

    # ------------------------------------------------------------------
    # locate — 三级降级
    # ------------------------------------------------------------------

    def locate(self, target: str) -> Optional[Coord]:
        """三级降级定位：控件树 → 局部 OCR → 返回 None（升级到 vision 由上层处理）。

        返回 None + logs T_CTRL/T_OCR 不满足时，上层 BackendManager 据此切 vision。
        """
        nodes = self._last_nodes
        if not nodes:
            self.observe()
            nodes = self._last_nodes

        # --- 第一级：控件树直接匹配 ---
        hit = self._match_node(nodes, target)
        if hit is not None:
            logger.debug("uia locate '%s' 控件树命中 bounds=%s", target, hit.bounds)
            return hit.center

        # --- 第二级：缺字段节点做局部 OCR ---
        # 取缺少 text/content-desc 但有 bounds 的节点做 OCR
        ocr_candidates = [
            n for n in nodes
            if not n.text and not n.content_desc and n.bounds != (0, 0, 0, 0)
        ]
        hit_rate = (len(nodes) - len(ocr_candidates)) / max(len(nodes), 1)

        if hit_rate < settings.t_ctrl and _OCR_ENGINE is not None:
            logger.debug(
                "uia locate '%s' 控件树命中率 %.2f < T_CTRL=%.2f，尝试局部 OCR（%d 节点）",
                target, hit_rate, settings.t_ctrl, len(ocr_candidates),
            )
            for node in ocr_candidates:
                ocr_text, conf = _ocr_region(self.serial, node.bounds)
                if conf < settings.t_ocr:
                    continue
                if target.lower() in ocr_text.lower() or ocr_text.lower() in target.lower():
                    logger.debug(
                        "局部 OCR 命中 '%s' conf=%.2f bounds=%s", ocr_text, conf, node.bounds
                    )
                    return node.center

        # --- 未命中：记录日志，返回 None，上层据此升 vision ---
        logger.info(
            "uia locate '%s' 未命中（hit_rate=%.2f，控件树节点数=%d）→ 需升级 vision",
            target, hit_rate, len(nodes),
        )
        return None

    def _match_node(self, nodes: list[UINode], target: str) -> Optional[UINode]:
        """在控件树中按 text / content-desc / resource-id 匹配目标。"""
        t = target.lower()
        # 优先精确匹配 text
        for node in nodes:
            if node.text and node.text.lower() == t:
                return node
        # 其次 content-desc 精确
        for node in nodes:
            if node.content_desc and node.content_desc.lower() == t:
                return node
        # 再次 text / content-desc 包含
        for node in nodes:
            if node.text and t in node.text.lower():
                return node
            if node.content_desc and t in node.content_desc.lower():
                return node
        # resource-id 末段匹配（去 package 前缀）
        for node in nodes:
            rid = node.resource_id.split("/")[-1].lower() if node.resource_id else ""
            if rid and t in rid:
                return node
        return None

    # ------------------------------------------------------------------
    # act
    # ------------------------------------------------------------------

    def act(self, action: Action) -> None:
        """执行动作，全部走 AdbDevice 非特权命令。"""
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
                # 中文走 ADBKeyboard
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
