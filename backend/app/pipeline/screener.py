"""
screener — 唯一投递权威（AC5/plan §4）。

流程（LangGraph 子图）：
  1. hard_filter 节点：城市/薪资/学历硬规则过滤，不通过直接 FAILED。
  2. llm_score 节点：gpt-5.5 文本打分 {score:0-100, reasons:[str]}。
  3. threshold 节点：score >= SCORE_THRESHOLD 置 CLAIMED，否则 FAILED。

"是否投递"决策权仅属此模块，pipeline 外无任何代码直接置 CLAIMED。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.models import Application, ApplicationStatus, Job


# ---------------------------------------------------------------------------
# 硬规则配置（可由 Config 表覆盖，此处为默认值）
# ---------------------------------------------------------------------------

DEFAULT_HARD_RULES: dict[str, Any] = {
    # 允许城市列表（空表示不限）
    "allowed_cities": [],
    # 最低薪资（K/月，0=不限）
    "min_salary_k": 0,
}


def _parse_salary_min(salary: str) -> float:
    """从薪资字符串中提取最低值（K/月）。如 '15-25K' -> 15.0。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~]\s*\d+\s*[Kk]", salary)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Kk]", salary)
    if m:
        return float(m.group(1))
    return 0.0


# ---------------------------------------------------------------------------
# LangGraph 状态
# ---------------------------------------------------------------------------


class ScreenerState(TypedDict):
    job: Job
    application_id: int
    hard_rules: dict
    passed_hard: bool
    score: float
    reasons: list[str]
    final_status: str  # "CLAIMED" | "FAILED"
    fail_reason: str


# ---------------------------------------------------------------------------
# 节点函数
# ---------------------------------------------------------------------------


def hard_filter(state: ScreenerState) -> ScreenerState:
    """硬规则过滤：城市 + 薪资下限。"""
    job = state["job"]
    rules = state["hard_rules"]

    allowed_cities: list[str] = rules.get("allowed_cities", [])
    min_salary_k: float = float(rules.get("min_salary_k", 0))

    if allowed_cities and not any(c in job.area for c in allowed_cities):
        return {
            **state,
            "passed_hard": False,
            "final_status": "FAILED",
            "fail_reason": f"城市不匹配: {job.area}",
        }

    if min_salary_k > 0:
        salary_min = _parse_salary_min(job.salary)
        if salary_min < min_salary_k:
            return {
                **state,
                "passed_hard": False,
                "final_status": "FAILED",
                "fail_reason": f"薪资低于下限: {job.salary}",
            }

    return {**state, "passed_hard": True}


def llm_score(state: ScreenerState) -> ScreenerState:
    """调用 gpt-5.5 为岗位打分（0-100）。"""
    if not state["passed_hard"]:
        return state

    from app.llm.client import llm_client  # 延迟导入，避免循环

    job = state["job"]
    prompt = (
        "你是一位求职助理，请对以下岗位进行评分（0-100分），并给出简短理由列表。\n\n"
        f"职位：{job.title}\n公司：{job.company}\n薪资：{job.salary}\n"
        f"城市：{job.area}\nJD：{job.jd[:500]}\n\n"
        "请以 JSON 格式回答：{{\"score\": <int>, \"reasons\": [<str>, ...]}}"
    )
    try:
        result = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            json_mode=True,
        )
        data = json.loads(result) if isinstance(result, str) else result
        score = float(data.get("score", 0))
        reasons = data.get("reasons", [])
    except Exception as e:
        # LLM 失败时保守处理：score=0
        score = 0.0
        reasons = [f"LLM 评分失败: {e}"]

    return {**state, "score": score, "reasons": reasons}


def apply_threshold(state: ScreenerState) -> ScreenerState:
    """score >= threshold 置 CLAIMED，否则 FAILED。"""
    if not state["passed_hard"]:
        return state

    threshold = settings.score_threshold
    if state["score"] >= threshold:
        return {**state, "final_status": "CLAIMED"}
    else:
        return {
            **state,
            "final_status": "FAILED",
            "fail_reason": f"score={state['score']:.1f} < threshold={threshold}",
        }


def _route_after_hard(state: ScreenerState) -> str:
    return "llm_score" if state["passed_hard"] else "write_result"


def write_result(state: ScreenerState) -> ScreenerState:
    """将最终状态写回 DB（Application + Job.score/reasons）。"""
    with Session(engine) as session:
        app = session.get(Application, state["application_id"])
        if app is None:
            return state

        final = state["final_status"]
        app.status = ApplicationStatus.CLAIMED if final == "CLAIMED" else ApplicationStatus.FAILED
        app.fail_reason = state.get("fail_reason", "")
        app.updated_at = datetime.utcnow()
        session.add(app)

        # 更新 Job 打分
        job = session.get(Job, state["job"].id)
        if job and state["score"] > 0:
            job.score = state["score"]
            job.reasons = json.dumps(state["reasons"], ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            session.add(job)

        session.commit()

    return state


# ---------------------------------------------------------------------------
# 构建 LangGraph 子图
# ---------------------------------------------------------------------------


def _build_graph() -> Any:
    builder = StateGraph(ScreenerState)
    builder.add_node("hard_filter", hard_filter)
    builder.add_node("llm_score", llm_score)
    builder.add_node("apply_threshold", apply_threshold)
    builder.add_node("write_result", write_result)

    builder.set_entry_point("hard_filter")
    builder.add_conditional_edges(
        "hard_filter",
        _route_after_hard,
        {"llm_score": "llm_score", "write_result": "write_result"},
    )
    builder.add_edge("llm_score", "apply_threshold")
    builder.add_edge("apply_threshold", "write_result")
    builder.add_edge("write_result", END)

    return builder.compile()


_graph = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def screen_application(
    application_id: int,
    hard_rules: dict | None = None,
) -> dict:
    """
    对单个 Application 执行筛选。
    返回 {"status": "CLAIMED"|"FAILED", "score": float, "reasons": list[str]}。
    """
    if hard_rules is None:
        hard_rules = DEFAULT_HARD_RULES.copy()

    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None:
            return {"status": "FAILED", "score": 0, "reasons": ["Application not found"]}
        job = session.get(Job, app.job_id)
        if job is None:
            return {"status": "FAILED", "score": 0, "reasons": ["Job not found"]}
        # detach copies for graph
        job_copy = Job.model_validate(job.model_dump())

    initial: ScreenerState = {
        "job": job_copy,
        "application_id": application_id,
        "hard_rules": hard_rules,
        "passed_hard": False,
        "score": 0.0,
        "reasons": [],
        "final_status": "FAILED",
        "fail_reason": "",
    }

    final_state = _get_graph().invoke(initial)
    return {
        "status": final_state["final_status"],
        "score": final_state["score"],
        "reasons": final_state["reasons"],
    }
