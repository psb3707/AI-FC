"""Streamlit AppTest (mock 모드, 외부 호출 없음). Filter 변경·Action-First 구조·Disclaimer·DEMO 배너 검증."""
import pytest
from streamlit.testing.v1 import AppTest

from src.config import ROOT
from src.models import AGE_CODES


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def texts(at):
    out = [m.value for m in at.markdown] + [c.value for c in at.caption] + [e.value for e in at.error]
    out += [s.value for s in at.subheader] + [i.value for i in at.info] + [w.value for w in at.warning]
    return "\n".join(out)


def test_mock_banner_and_disclaimer_summary(at):
    t = texts(at)
    assert "DEMO DATA" in t
    assert "검색 관심도의 상대적 변화" in t and "판매량" in t and "필요성" in t


def test_action_first_order_and_sections(at):
    subs = [s.value for s in at.subheader]
    assert subs[0].endswith("이번 달 상담 준비")  # Signal/Check Point 가 Card·Chart 보다 먼저
    assert subs.index("Topic별 관심 변화") < subs.index("왜 이렇게 판단했나 · 관심도 추이") < subs.index("AI 해석")
    t = texts(at)
    for needle in ("이번 달 주목 Signal", "FC Check Point", "상담 시작 질문", "무엇이 변했나", "어떻게 해석하나", "무엇을 물어볼까", "SFA"):
        assert needle in t, needle


def test_cards_show_direction_not_raw_index(at):
    t = texts(at)
    assert "최근 3개월 평균 대비" in t and "전월 대비" in t
    assert "검색 관심지수:" not in t  # Raw 지수는 Card 가 아니라 상세 지표로


@pytest.mark.parametrize("age", list(AGE_CODES))
@pytest.mark.parametrize("gender", ["male", "female", "all"])
def test_age_gender_filters(at, age, gender):
    at.selectbox[0].set_value(age)
    at.radio[0].set_value(gender)
    at.run()
    assert not at.exception, at.exception
    assert at.subheader[0].value.endswith("이번 달 상담 준비")


@pytest.mark.parametrize("months", [6, 12, 24])
def test_period_filter(at, months):
    at.selectbox[1].set_value(months)
    at.run()
    assert not at.exception, at.exception


def test_topic_selector_for_chart(at):
    topic_box = next(s for s in at.selectbox if s.label == "Topic")
    for name in topic_box.options:
        topic_box.set_value(name)
        at.run()
        assert not at.exception, at.exception
        topic_box = next(s for s in at.selectbox if s.label == "Topic")
