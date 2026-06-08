"""应用信息查询 — dumpsys window 解析前台包名/Activity。"""

from __future__ import annotations

import re
from typing import Optional

from app.adb._run import run_adb


# 匹配 mCurrentFocus=Window{... package/activity}
# Android 不同版本输出格式略有差异，两条正则覆盖主流情况
_FOCUS_RE_LIST = [
    # Android 10+: mCurrentFocus=Window{hash u0 package/activity}
    re.compile(r"mCurrentFocus=Window\{[^}]+\s+(\S+)/(\S+)\}"),
    # 部分旧版: mFocusedApp=...ActivityRecord{... package/.activity ...}
    re.compile(r"mFocusedApp=.*?ActivityRecord\{[^}]+\s+(\S+)/(\S+)\s"),
]

# 匹配 mTopResumedActivity 格式（Android 11+）
_TOP_RESUMED_RE = re.compile(
    r"mTopResumedActivity=ActivityRecord\{[^}]+\s+(\S+)/(\S+)\s"
)


def _parse_window_focus(output: str) -> Optional[tuple[str, str]]:
    """从 dumpsys window 输出中提取 (package, activity) 元组。"""
    for pattern in _FOCUS_RE_LIST:
        m = pattern.search(output)
        if m:
            return m.group(1), m.group(2)
    return None


def _parse_top_resumed(output: str) -> Optional[tuple[str, str]]:
    m = _TOP_RESUMED_RE.search(output)
    if m:
        return m.group(1), m.group(2)
    return None


def get_foreground_package(serial: str, *, timeout: float = 10.0) -> Optional[str]:
    """返回当前前台应用包名，解析失败返回 None。"""
    result = run_adb(serial, ["shell", "dumpsys", "window"], check=False, timeout=timeout)
    pair = _parse_window_focus(result.stdout) or _parse_top_resumed(result.stdout)
    return pair[0] if pair else None


def get_foreground_activity(serial: str, *, timeout: float = 10.0) -> Optional[str]:
    """返回当前前台 Activity 全名（package/activity），解析失败返回 None。"""
    result = run_adb(serial, ["shell", "dumpsys", "window"], check=False, timeout=timeout)
    pair = _parse_window_focus(result.stdout) or _parse_top_resumed(result.stdout)
    if pair is None:
        return None
    pkg, act = pair
    # 补全相对 Activity 名（以 . 开头）
    if act.startswith("."):
        act = pkg + act
    return f"{pkg}/{act}"


def is_foreground(serial: str, package: str, *, timeout: float = 10.0) -> bool:
    """判断指定包是否在前台。"""
    return get_foreground_package(serial, timeout=timeout) == package
