"""
list_page — Boss 直聘岗位列表页对象。

职责：
  - 抓取当前屏幕岗位卡片列表（委托 backend.observe()）
  - 滚动加载更多
  - ensure_anchor()：从任意页面导航回列表页（锚点页）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.pages.base_page import BasePage

if TYPE_CHECKING:
    from app.backends.base import ControlBackend


class ListPage(BasePage):
    PAGE_NAME = "job_list"

    # Boss 直聘岗位列表页的 package/activity（可由 Config 覆盖）
    BOSS_PACKAGE = "com.hpbr.bosszhipin"
    LIST_ACTIVITY = "com.hpbr.bosszhipin.module.joblist.JobListActivity"

    def __init__(self, backend: "ControlBackend") -> None:
        super().__init__(backend)

    def get_job_cards(self) -> list[dict]:
        """
        抓取当前屏幕所有岗位卡片。
        返回 list[{title, company, salary, area}]。
        依赖 backend.observe() 返回的控件树或 OCR 结构。
        """
        snapshot = self.observe()
        cards = snapshot.get("job_cards", [])
        return cards

    def scroll_down(self) -> bool:
        """向下滚动一屏，加载更多岗位。"""
        return self.act({"type": "swipe", "direction": "up", "distance": 800})

    def tap_job(self, index: int) -> bool:
        """点击第 index 个岗位卡片（0-based）。"""
        target = f"job_card_{index}"
        coord = self.locate(target)
        if coord is None:
            return False
        return self.act({"type": "tap", "x": coord[0], "y": coord[1]})

    def ensure_anchor(self) -> bool:
        """
        导航回岗位列表页（锚点页）。
        策略：按 HOME 键后重新启动 Boss 直聘到列表页。
        """
        # 先尝试点击底部"职位"tab（最轻量）
        coord = self.locate("tab_jobs")
        if coord:
            self.act({"type": "tap", "x": coord[0], "y": coord[1]})
            return True
        # 兜底：启动 Activity
        return self.act({
            "type": "launch",
            "package": self.BOSS_PACKAGE,
            "activity": self.LIST_ACTIVITY,
        })
