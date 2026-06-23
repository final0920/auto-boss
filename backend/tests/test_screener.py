"""
tests/test_screener.py — screener 纯函数单测。

覆盖：
  - parse_salary / parse_degree / parse_experience / parse_hr_active 边界
  - prefilter 各规则（薪资/城市/区域/关键词/学历/经验）
  - screen 详情级缺失字段放行+标注、LLM mock 打分阈值
  - 薪资区间相交真值表
  - apply_screen_result DB 写入

测试全 mock LLM，不真实调用 API。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from app.models import Application, ApplicationStatus, Job
from app.pipeline.screener import (
    ScreenResult,
    apply_screen_result,
    parse_degree,
    parse_experience,
    parse_hr_active,
    parse_salary,
    prefilter,
    screen,
)
from app.rules import RulesConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_job(**kwargs) -> Job:
    """创建测试用 Job 对象（不落库）。"""
    defaults = dict(
        id=1,
        title="Python 后端工程师",
        company="测试科技",
        salary="15-25K",
        area="上海",
        jd="负责后端开发",
        jd_hash="abc123",
        score=None,
        reasons="",
        degree="",
        experience="",
        company_scale="",
        finance_stage="",
        hr_active="",
        hr_name="",
        detail_fetched_at=None,
    )
    defaults.update(kwargs)
    return Job(**defaults)


def make_rules(**kwargs) -> RulesConfig:
    defaults = dict(
        salary_min_k=0,
        salary_max_k=0,
        allowed_cities=[],
        blocked_areas=[],
        include_keywords=[],
        exclude_keywords=[],
        company_scales=[],
        my_degree="",
        my_experience_years=0,
        hr_active_within_days=0,
        dedup_contacted=True,
        llm_threshold=80,
        profile="",
        greeting_prompt="",
        daily_limit=100,
        interval_min_sec=20,
        interval_max_sec=90,
        morning_start="09:00",
        morning_end="12:00",
        afternoon_start="14:00",
        afternoon_end="18:00",
    )
    defaults.update(kwargs)
    return RulesConfig(**defaults)


# ---------------------------------------------------------------------------
# parse_salary
# ---------------------------------------------------------------------------


class TestParseSalary:
    def test_k_range(self):
        assert parse_salary("10-15K·13薪") == (10.0, 15.0)

    def test_k_range_simple(self):
        assert parse_salary("20-30K") == (20.0, 30.0)

    def test_yuan_per_month(self):
        lo, hi = parse_salary("2000-150000元/月")
        assert lo == pytest.approx(2.0, rel=0.01)
        assert hi == pytest.approx(150.0, rel=0.01)

    def test_mianyi(self):
        assert parse_salary("面议") == (0.0, 0.0)

    def test_empty(self):
        assert parse_salary("") == (0.0, 0.0)

    def test_none_like(self):
        # None 不传入（类型约束），但空串等价于解析失败
        assert parse_salary("N/A") == (0.0, 0.0)

    def test_single_k(self):
        lo, hi = parse_salary("15K")
        assert lo == 15.0 and hi == 15.0

    def test_decimal_k(self):
        lo, hi = parse_salary("12.5-17.5K")
        assert lo == pytest.approx(12.5) and hi == pytest.approx(17.5)

    def test_garbage(self):
        assert parse_salary("待遇丰厚") == (0.0, 0.0)


# ---------------------------------------------------------------------------
# parse_degree
# ---------------------------------------------------------------------------


class TestParseDegree:
    def test_buxi(self):
        assert parse_degree("不限") == 0

    def test_gaogzhong(self):
        assert parse_degree("高中") == 1

    def test_zhongzhuan(self):
        assert parse_degree("中专") == 2

    def test_zhongji(self):
        assert parse_degree("中技") == 2

    def test_dazhuan(self):
        assert parse_degree("大专") == 3

    def test_benke(self):
        assert parse_degree("本科") == 4

    def test_benke_jiyi_shang(self):
        assert parse_degree("本科及以上") == 4

    def test_shuoshi(self):
        assert parse_degree("硕士") == 5

    def test_boshi(self):
        assert parse_degree("博士") == 6

    def test_empty(self):
        assert parse_degree("") == 0

    def test_unknown(self):
        assert parse_degree("其他学历") == 0


# ---------------------------------------------------------------------------
# parse_experience
# ---------------------------------------------------------------------------


class TestParseExperience:
    def test_range(self):
        assert parse_experience("1-3年") == 1

    def test_range_35(self):
        assert parse_experience("3-5年") == 3

    def test_10_years_plus(self):
        assert parse_experience("10年以上") == 10

    def test_buxian(self):
        assert parse_experience("经验不限") == 0

    def test_yingjie(self):
        assert parse_experience("应届") == 0

    def test_empty(self):
        assert parse_experience("") == 0

    def test_pure_years(self):
        assert parse_experience("3年") == 3

    def test_garbage(self):
        assert parse_experience("无要求") == 0


# ---------------------------------------------------------------------------
# parse_hr_active
# ---------------------------------------------------------------------------


class TestParseHrActive:
    def test_online(self):
        assert parse_hr_active("在线") == 1

    def test_just_now(self):
        assert parse_hr_active("刚刚活跃") == 1

    def test_today(self):
        assert parse_hr_active("今日活跃") == 1

    def test_3days(self):
        assert parse_hr_active("3日内活跃") == 3

    def test_this_week(self):
        assert parse_hr_active("本周活跃") == 7

    def test_this_month(self):
        assert parse_hr_active("本月活跃") == 30

    def test_unknown_text(self):
        # 有活跃词但无法解析具体天数 -> 999
        assert parse_hr_active("半年前活跃") == 999

    def test_empty(self):
        assert parse_hr_active("") is None

    def test_none_like(self):
        assert parse_hr_active(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 薪资区间相交真值表
# ---------------------------------------------------------------------------


class TestSalaryIntersects:
    """通过 prefilter 验证薪资相交逻辑。"""

    def _pf(self, job_salary: str, rule_min: float, rule_max: float) -> bool:
        job = make_job(salary=job_salary)
        rules = make_rules(salary_min_k=rule_min, salary_max_k=rule_max)
        passed, _ = prefilter(job, rules)
        return passed

    def test_job_within_rule(self):
        assert self._pf("15-25K", 10, 30) is True

    def test_job_above_rule_max(self):
        assert self._pf("35-50K", 10, 30) is False

    def test_job_below_rule_min(self):
        assert self._pf("5-8K", 10, 30) is False

    def test_partial_overlap_high(self):
        # 20-30K 和规则 10-25K 有交集
        assert self._pf("20-30K", 10, 25) is True

    def test_partial_overlap_low(self):
        # 8-12K 和规则 10-20K 有交集
        assert self._pf("8-12K", 10, 20) is True

    def test_job_mianyi_passthrough(self):
        # 面议 -> (0,0) 放行
        assert self._pf("面议", 10, 30) is True

    def test_rule_no_limit(self):
        assert self._pf("5-8K", 0, 0) is True

    def test_rule_only_min(self):
        # max=0 表示无上限
        assert self._pf("20-30K", 15, 0) is True

    def test_rule_only_min_fail(self):
        assert self._pf("5-8K", 15, 0) is False


# ---------------------------------------------------------------------------
# prefilter 各规则
# ---------------------------------------------------------------------------


class TestPrefilter:
    def test_pass_all_empty_rules(self):
        job = make_job()
        passed, reason = prefilter(job, make_rules())
        assert passed is True
        assert reason == ""

    def test_allowed_cities_pass(self):
        job = make_job(area="上海浦东")
        rules = make_rules(allowed_cities=["上海"])
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_allowed_cities_fail(self):
        job = make_job(area="北京朝阳")
        rules = make_rules(allowed_cities=["上海"])
        passed, reason = prefilter(job, rules)
        assert passed is False
        assert "城市" in reason

    def test_blocked_areas_fail(self):
        job = make_job(area="上海浦东")
        rules = make_rules(blocked_areas=["浦东"])
        passed, reason = prefilter(job, rules)
        assert passed is False
        assert "黑名单" in reason

    def test_include_keywords_pass(self):
        job = make_job(title="高级 Python 后端工程师")
        rules = make_rules(include_keywords=["Python"])
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_include_keywords_not_checked_at_list_level(self):
        """include_keywords 不做列表级否决：标题不含也放行，留给详情级对 title+jd 判定
        （列表页抓不到 JD，标题不含 ≠ JD 不含，避免误杀）。"""
        job = make_job(title="后端开发工程师")
        rules = make_rules(include_keywords=["Python"])
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_exclude_keywords_title(self):
        job = make_job(title="外包 Python 工程师")
        rules = make_rules(exclude_keywords=["外包"])
        passed, reason = prefilter(job, rules)
        assert passed is False
        assert "外包" in reason

    def test_exclude_keywords_company(self):
        job = make_job(company="某外包公司")
        rules = make_rules(exclude_keywords=["外包"])
        passed, reason = prefilter(job, rules)
        assert passed is False

    def test_degree_filter_pass(self):
        # 岗位要求本科，我是本科 -> 通过
        job = make_job(degree="本科")
        rules = make_rules(my_degree="本科")
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_degree_filter_fail(self):
        # 岗位要求硕士，我是本科 -> 失败
        job = make_job(degree="硕士")
        rules = make_rules(my_degree="本科")
        passed, reason = prefilter(job, rules)
        assert passed is False
        assert "学历" in reason

    def test_degree_empty_passthrough(self):
        # job.degree 为空 -> 放行
        job = make_job(degree="")
        rules = make_rules(my_degree="本科")
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_experience_filter_pass(self):
        job = make_job(experience="1-3年")
        rules = make_rules(my_experience_years=2)
        passed, _ = prefilter(job, rules)
        assert passed is True

    def test_experience_filter_fail(self):
        job = make_job(experience="5-10年")
        rules = make_rules(my_experience_years=2)
        passed, reason = prefilter(job, rules)
        assert passed is False
        assert "经验" in reason

    def test_experience_empty_passthrough(self):
        job = make_job(experience="")
        rules = make_rules(my_experience_years=2)
        passed, _ = prefilter(job, rules)
        assert passed is True


# ---------------------------------------------------------------------------
# screen — 详情级，LLM mock
# ---------------------------------------------------------------------------


def _mock_llm_response(score: int, reasons: list[str]) -> str:
    return json.dumps({"score": score, "reasons": reasons})


class TestScreen:
    def _run_screen(self, job: Job, rules: RulesConfig, llm_score: int = 85) -> ScreenResult:
        with patch("app.llm.client.get_client") as mock_gc:
            client = MagicMock()
            client.chat.return_value = _mock_llm_response(llm_score, ["匹配度高"])
            mock_gc.return_value = client
            return screen(job, rules)

    def test_pass_llm_above_threshold(self):
        job = make_job()
        rules = make_rules(llm_threshold=80)
        result = self._run_screen(job, rules, llm_score=85)
        assert result.final == "CLAIMED"
        assert result.passed_hard is True
        assert result.score == pytest.approx(85.0)

    def test_fail_llm_below_threshold(self):
        job = make_job()
        rules = make_rules(llm_threshold=80)
        result = self._run_screen(job, rules, llm_score=70)
        assert result.final == "FAILED"
        assert "阈值" in result.fail_reason or "评分" in result.fail_reason

    def test_exact_threshold_passes(self):
        job = make_job()
        rules = make_rules(llm_threshold=80)
        result = self._run_screen(job, rules, llm_score=80)
        assert result.final == "CLAIMED"

    def test_exclude_keyword_in_jd_fails_hard(self):
        job = make_job(jd="需要负责外包项目管理")
        rules = make_rules(exclude_keywords=["外包"])
        result = self._run_screen(job, rules, llm_score=90)
        assert result.final == "FAILED"
        assert result.passed_hard is False

    def test_missing_company_scale_passthrough(self):
        # company_scale 字段为空，规则设了过滤 -> 放行 + missing 标注
        job = make_job(company_scale="")
        rules = make_rules(company_scales=["100-499人"])
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True
        assert any("missing:company_scale" in r for r in result.reasons)

    def test_company_scale_mismatch_fails(self):
        job = make_job(company_scale="0-20人")
        rules = make_rules(company_scales=["100-499人"])
        result = self._run_screen(job, rules, llm_score=85)
        assert result.final == "FAILED"
        assert result.passed_hard is False

    def test_missing_degree_passthrough(self):
        job = make_job(degree="")
        rules = make_rules(my_degree="本科")
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True
        assert any("missing:degree" in r for r in result.reasons)

    def test_missing_experience_passthrough(self):
        job = make_job(experience="")
        rules = make_rules(my_experience_years=3)
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True
        assert any("missing:experience" in r for r in result.reasons)

    def test_missing_hr_active_passthrough(self):
        job = make_job(hr_active="")
        rules = make_rules(hr_active_within_days=7)
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True
        assert any("missing:hr_active" in r for r in result.reasons)

    def test_hr_active_too_old_fails(self):
        job = make_job(hr_active="本月活跃")   # 30 天
        rules = make_rules(hr_active_within_days=7)
        result = self._run_screen(job, rules, llm_score=85)
        assert result.final == "FAILED"
        assert result.passed_hard is False

    def test_hr_active_ok_passes(self):
        job = make_job(hr_active="今日活跃")   # 1 天
        rules = make_rules(hr_active_within_days=7)
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True

    def test_llm_error_falls_back_score_zero(self):
        """LLM 异常时 score=0，低于阈值 -> FAILED，不崩溃。"""
        job = make_job()
        rules = make_rules(llm_threshold=80)
        with patch("app.llm.client.get_client") as mock_gc:
            client = MagicMock()
            client.chat.side_effect = RuntimeError("network error")
            mock_gc.return_value = client
            result = screen(job, rules)
        assert result.final == "FAILED"
        assert result.score == pytest.approx(0.0)
        assert any("LLM" in r for r in result.reasons)

    def test_include_keywords_in_jd_passes(self):
        job = make_job(title="工程师", jd="负责 Python 微服务开发")
        rules = make_rules(include_keywords=["Python"])
        result = self._run_screen(job, rules, llm_score=85)
        assert result.passed_hard is True

    def test_include_keywords_neither_title_nor_jd_fails(self):
        job = make_job(title="Java 工程师", jd="负责后端开发")
        rules = make_rules(include_keywords=["Python"])
        result = self._run_screen(job, rules, llm_score=85)
        assert result.final == "FAILED"
        assert result.passed_hard is False

    def test_profile_included_in_prompt(self):
        """profile 非空时应传入 LLM prompt。"""
        job = make_job()
        rules = make_rules(profile="5年 Python 经验，擅长分布式系统", llm_threshold=80)
        with patch("app.llm.client.get_client") as mock_gc:
            client = MagicMock()
            client.chat.return_value = _mock_llm_response(85, [])
            mock_gc.return_value = client
            screen(job, rules)
            call_args = client.chat.call_args
            prompt_text = call_args[1]["messages"][0]["content"]
            assert "5年 Python 经验" in prompt_text


# ---------------------------------------------------------------------------
# apply_screen_result — DB 写入（内存 SQLite）
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_session():
    """创建内存 SQLite + 必要表结构，返回 Session。"""
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_app(session, status=ApplicationStatus.PENDING) -> tuple[int, int]:
    """向 session 写入一条 Job + Application，返回 (job_id, app_id)。"""
    from datetime import datetime

    job = Job(
        title="测试岗位",
        company="测试公司",
        salary="20K",
        area="上海",
        jd="test",
        jd_hash="seed001",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(job)
    session.flush()

    app = Application(
        job_id=job.id,
        account_id="default",
        device_id="default",
        status=status,
    )
    session.add(app)
    session.flush()
    session.commit()
    return job.id, app.id


class TestApplyScreenResult:
    def test_claimed_writes_status(self, memory_session):
        job_id, app_id = _seed_app(memory_session)
        result = ScreenResult(
            passed_hard=True, score=88.0, reasons=["好岗位"], final="CLAIMED", fail_reason=""
        )
        apply_screen_result(memory_session, app_id, result)
        app = memory_session.get(Application, app_id)
        assert app.status == ApplicationStatus.CLAIMED
        assert app.fail_reason == ""

    def test_failed_writes_status_and_reason(self, memory_session):
        job_id, app_id = _seed_app(memory_session)
        result = ScreenResult(
            passed_hard=False, score=0.0, reasons=[], final="FAILED", fail_reason="薪资不匹配"
        )
        apply_screen_result(memory_session, app_id, result)
        app = memory_session.get(Application, app_id)
        assert app.status == ApplicationStatus.FAILED
        assert app.fail_reason == "薪资不匹配"

    def test_score_written_to_job(self, memory_session):
        job_id, app_id = _seed_app(memory_session)
        result = ScreenResult(
            passed_hard=True, score=92.0, reasons=["技术匹配", "薪资合理"], final="CLAIMED"
        )
        apply_screen_result(memory_session, app_id, result)
        job = memory_session.get(Job, job_id)
        assert job.score == pytest.approx(92.0)
        reasons_list = json.loads(job.reasons)
        assert "技术匹配" in reasons_list

    def test_score_zero_not_written_to_job(self, memory_session):
        job_id, app_id = _seed_app(memory_session)
        result = ScreenResult(
            passed_hard=False, score=0.0, reasons=[], final="FAILED", fail_reason="硬过滤"
        )
        apply_screen_result(memory_session, app_id, result)
        job = memory_session.get(Job, job_id)
        assert job.score is None  # 原始值未被覆写

    def test_nonexistent_app_no_crash(self, memory_session):
        result = ScreenResult(final="CLAIMED", score=90.0, passed_hard=True)
        # 不应抛出异常
        apply_screen_result(memory_session, 9999, result)
