"""
detail_page — Boss 直聘岗位详情页对象。

职责：
  - 读取 JD 详细文本
  - 定位并点击"立即沟通"按钮（dispatcher 调用）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.pages.base_page import BasePage

if TYPE_CHECKING:
    from app.backends.base import ControlBackend


class DetailPage(BasePage):
    PAGE_NAME = "job_detail"

    def __init__(self, backend: "ControlBackend") -> None:
        super().__init__(backend)

    def get_jd_text(self) -> str:
        """读取 JD 正文（控件树文本 or OCR）。"""
        snapshot = self.observe()
        return snapshot.get("jd_text", "")

    def get_job_meta(self) -> dict:
        """读取薪资/城市/学历等元数据。"""
        snapshot = self.observe()
        return snapshot.get("job_meta", {})

    def tap_communicate(self) -> bool:
        """
        点击"立即沟通"按钮。
        dispatcher 在 SENDING 阶段调用此方法（唯一入口）。
        返回 True 表示成功点击，False 表示未找到按钮。
        """
        coord = self.wait_for("btn_communicate", max_attempts=5)
        if coord is None:
            return False
        return self.act({"type": "tap", "x": coord[0], "y": coord[1]})

    def is_geetest_visible(self) -> bool:
        """检测 geetest 验证码是否出现。"""
        snapshot = self.observe()
        return snapshot.get("geetest_visible", False)
