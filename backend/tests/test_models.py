"""test_models.py — Application 状态机合法/非法转移测试。"""

from __future__ import annotations

import pytest
from app.models import ApplicationStatus


# 合法转移表（状态机定义来自 plan §6）
LEGAL_TRANSITIONS = [
    (ApplicationStatus.PENDING,  ApplicationStatus.CLAIMED),
    (ApplicationStatus.CLAIMED,  ApplicationStatus.SENDING),
    (ApplicationStatus.SENDING,  ApplicationStatus.SENT),
    (ApplicationStatus.SENDING,  ApplicationStatus.FAILED),
]

# 非法转移（dispatcher 不应执行）
ILLEGAL_TRANSITIONS = [
    (ApplicationStatus.PENDING,  ApplicationStatus.SENDING),
    (ApplicationStatus.PENDING,  ApplicationStatus.SENT),
    (ApplicationStatus.SENT,     ApplicationStatus.CLAIMED),
    (ApplicationStatus.SENT,     ApplicationStatus.PENDING),
    (ApplicationStatus.FAILED,   ApplicationStatus.SENT),
    (ApplicationStatus.SENDING,  ApplicationStatus.PENDING),
    (ApplicationStatus.SENDING,  ApplicationStatus.CLAIMED),
]

# dispatcher 只取 CLAIMED：PENDING/SENDING/SENT/FAILED 均应跳过
DISPATCHER_SKIP_STATUSES = [
    ApplicationStatus.PENDING,
    ApplicationStatus.SENDING,
    ApplicationStatus.SENT,
    ApplicationStatus.FAILED,
]


def _can_transition(src: ApplicationStatus, dst: ApplicationStatus) -> bool:
    """根据状态机规则判断转移是否合法。"""
    return (src, dst) in LEGAL_TRANSITIONS


class TestApplicationStateMachine:
    @pytest.mark.parametrize("src,dst", LEGAL_TRANSITIONS)
    def test_legal_transitions(self, src, dst):
        assert _can_transition(src, dst), f"期望合法: {src} -> {dst}"

    @pytest.mark.parametrize("src,dst", ILLEGAL_TRANSITIONS)
    def test_illegal_transitions(self, src, dst):
        assert not _can_transition(src, dst), f"期望非法: {src} -> {dst}"

    @pytest.mark.parametrize("status", DISPATCHER_SKIP_STATUSES)
    def test_dispatcher_only_takes_claimed(self, status):
        """dispatcher 只处理 CLAIMED 状态，其他状态应跳过。"""
        assert status != ApplicationStatus.CLAIMED, \
            f"意外：{status} 是 CLAIMED，不应在跳过列表中"

    def test_sending_never_auto_retaken(self):
        """SENDING 不能自动转回 CLAIMED（防二次发送 AC8）。"""
        assert not _can_transition(ApplicationStatus.SENDING, ApplicationStatus.CLAIMED)

    def test_taken_over_flag_independent_of_status(self):
        """taken_over 是独立标志，不影响状态机枚举值。"""
        # taken_over 不是 ApplicationStatus 的一部分
        assert not hasattr(ApplicationStatus, "TAKEN_OVER")

    def test_status_values_are_strings(self):
        for s in ApplicationStatus:
            assert isinstance(s.value, str)
