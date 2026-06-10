"""test_rules.py — RulesConfig 契约单测（§5.1）。"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from app.rules import RulesConfig, load_rules, save_rules


# ---------------------------------------------------------------------------
# 内存 DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# 1. 默认值完整性：19 字段全有默认
# ---------------------------------------------------------------------------

EXPECTED_FIELDS = {
    "salary_min_k",
    "salary_max_k",
    "allowed_cities",
    "blocked_areas",
    "include_keywords",
    "exclude_keywords",
    "company_scales",
    "my_degree",
    "my_experience_years",
    "hr_active_within_days",
    "dedup_contacted",
    "llm_threshold",
    "profile",
    "greeting_prompt",
    "daily_limit",
    "interval_min_sec",
    "interval_max_sec",
    "night_stop_start",
    "night_stop_end",
}


class TestRulesConfigDefaults:
    def test_all_19_fields_present(self):
        rc = RulesConfig()
        actual = set(rc.model_fields.keys())
        assert actual == EXPECTED_FIELDS, (
            f"字段不一致。多余: {actual - EXPECTED_FIELDS}，缺少: {EXPECTED_FIELDS - actual}"
        )

    def test_default_values_instantiate_without_error(self):
        rc = RulesConfig()
        assert rc.salary_min_k == 0
        assert rc.salary_max_k == 0
        assert rc.allowed_cities == []
        assert rc.blocked_areas == []
        assert rc.include_keywords == []
        assert rc.exclude_keywords == []
        assert rc.company_scales == []
        assert rc.my_degree == ""
        assert rc.my_experience_years == 0
        assert rc.hr_active_within_days == 0
        assert rc.dedup_contacted is True
        assert rc.llm_threshold == 80
        assert rc.profile == ""
        assert rc.greeting_prompt == ""
        assert rc.daily_limit == 100
        assert rc.interval_min_sec == 20
        assert rc.interval_max_sec == 90
        assert rc.night_stop_start == "23:00"
        assert rc.night_stop_end == "07:00"


# ---------------------------------------------------------------------------
# 2. round-trip: save_rules → load_rules 等值
# ---------------------------------------------------------------------------


class TestRulesRoundTrip:
    def test_default_round_trip(self, session: Session):
        rc = RulesConfig()
        save_rules(session, rc)
        loaded = load_rules(session)
        assert loaded == rc

    def test_custom_values_round_trip(self, session: Session):
        rc = RulesConfig(
            salary_min_k=15.0,
            salary_max_k=30.0,
            allowed_cities=["北京", "上海"],
            blocked_areas=["某区"],
            include_keywords=["Python"],
            exclude_keywords=["外包"],
            company_scales=["100-499人"],
            my_degree="本科",
            my_experience_years=3,
            hr_active_within_days=7,
            dedup_contacted=False,
            llm_threshold=75,
            profile="5年Python后端",
            greeting_prompt="",
            daily_limit=50,
            interval_min_sec=30,
            interval_max_sec=120,
            night_stop_start="22:00",
            night_stop_end="08:00",
        )
        save_rules(session, rc)
        loaded = load_rules(session)
        assert loaded == rc

    def test_overwrite_saves_latest(self, session: Session):
        rc1 = RulesConfig(daily_limit=50)
        save_rules(session, rc1)
        rc2 = RulesConfig(daily_limit=80)
        save_rules(session, rc2)
        loaded = load_rules(session)
        assert loaded.daily_limit == 80


# ---------------------------------------------------------------------------
# 3. extra="forbid": 未知字段引发 ValidationError
# ---------------------------------------------------------------------------


class TestRulesExtraForbid:
    def test_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            RulesConfig(unknown_field="should_fail")

    def test_model_validate_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            RulesConfig.model_validate({"salary_min_k": 10, "bogus": "x"})


# ---------------------------------------------------------------------------
# 4. load 损坏 JSON 回退默认值
# ---------------------------------------------------------------------------


class TestRulesLoadCorrupted:
    def test_corrupted_json_falls_back_to_default(self, session: Session):
        from app.models import Config
        from datetime import datetime

        row = Config(key="rules", value="{not valid json!!!}", updated_at=datetime.utcnow())
        session.add(row)
        session.commit()

        loaded = load_rules(session)
        assert loaded == RulesConfig()

    def test_missing_key_falls_back_to_default(self, session: Session):
        loaded = load_rules(session)
        assert loaded == RulesConfig()

    def test_empty_value_falls_back_to_default(self, session: Session):
        from app.models import Config
        from datetime import datetime

        row = Config(key="rules", value="", updated_at=datetime.utcnow())
        session.add(row)
        session.commit()

        loaded = load_rules(session)
        assert loaded == RulesConfig()
