"""
chat_page — Boss 直聘聊天页对象。

职责：
  - 读取 HR 消息列表（inbox_watcher 调用，强制走控件树，plan §4/AC7）
  - 发送打招呼语（dispatcher/executor 调用，经 ADBKeyboard，AC6）
  - 检测 geetest

注意：发送消息必须经 dispatcher 状态机 + RateLimiter，
      chat_page 本身不调用 rate_limiter（AC19）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.pages.base_page import BasePage

if TYPE_CHECKING:
    from app.backends.base import ControlBackend


class ChatPage(BasePage):
    PAGE_NAME = "chat"

    def __init__(self, backend: "ControlBackend") -> None:
        super().__init__(backend)

    # ------------------------------------------------------------------
    # 消息读取（inbox_watcher 使用，AC7：强制控件树）
    # ------------------------------------------------------------------

    def get_messages(self) -> list[dict]:
        """
        读取当前聊天页消息列表。
        返回 list[{role: "user"|"hr", text: str, ts: str}]。
        inbox_watcher 调用此方法时应确保 backend 为 uia（控件树）。
        """
        snapshot = self.observe()
        return snapshot.get("messages", [])

    def get_latest_hr_message(self) -> Optional[dict]:
        """返回最新一条 HR 消息，无则 None。"""
        messages = self.get_messages()
        hr_msgs = [m for m in messages if m.get("role") == "hr"]
        return hr_msgs[-1] if hr_msgs else None

    # ------------------------------------------------------------------
    # 发送消息（dispatcher/executor 调用，不经此处做配额检查）
    # ------------------------------------------------------------------

    def tap_input_box(self) -> bool:
        """点击聊天输入框。"""
        coord = self.wait_for("chat_input", max_attempts=5)
        if coord is None:
            return False
        return self.act({"type": "tap", "x": coord[0], "y": coord[1]})

    def input_text(self, text: str) -> bool:
        """
        向输入框输入文字（使用 ADBKeyboard broadcast，AC6 无乱码）。
        """
        return self.act({"type": "input_text", "text": text})

    def tap_send(self) -> bool:
        """点击发送按钮。"""
        coord = self.wait_for("btn_send", max_attempts=3)
        if coord is None:
            return False
        return self.act({"type": "tap", "x": coord[0], "y": coord[1]})

    def send_greeting(self, greeting: str) -> bool:
        """
        完整打招呼流程：点击输入框 -> 输入文字 -> 点击发送。
        仅由 dispatcher/executor 在确认 SENDING 状态后调用（AC19）。
        """
        if not self.tap_input_box():
            return False
        if not self.input_text(greeting):
            return False
        return self.tap_send()

    # ------------------------------------------------------------------
    # geetest 检测
    # ------------------------------------------------------------------

    def is_geetest_visible(self) -> bool:
        snapshot = self.observe()
        return snapshot.get("geetest_visible", False)
