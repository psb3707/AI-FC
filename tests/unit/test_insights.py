import json

import httpx
import pytest

from src.insights import get_provider
from src.insights.base import REQUIRED_DISCLAIMER, Brief, build_payload
from src.insights.guardrails import violations
from src.insights.llm_insight import OpenAIInsightProvider
from src.insights.template_insight import TemplateInsightProvider
from src.models import Segment, SegmentReport
from src.processing.normalizer import normalize
from src.processing.trend_calculator import compute_metrics


@pytest.fixture
def payload(naver_response, topics, cfg):
    recs = normalize(naver_response, topics, "4", "male")
    rep = SegmentReport(
        segment=Segment(age_code="4", gender="male"), data_source="real", records=recs,
        metrics=compute_metrics(recs, topics, cfg.trend),
    )
    return build_payload(rep, topics)


def mk(what="암보험 관심이 높게 나타났습니다.", interp=REQUIRED_DISCLAIMER, v=("q1",), d=("q2",)):
    return Brief(what_changed=what, interpretation=interp, validation_questions=list(v), deep_dive_questions=list(d))


def test_payload_has_only_computed_metrics(payload):
    assert payload["segment"]["label"] == "25~29세 남성" and payload["period"] == "2026-09"
    t = payload["topics"][0]
    assert set(t) == {"name", "mom_pct", "three_month_momentum_pct", "direction"}  # Raw 관심지수는 LLM 에 전달하지 않는다
    assert "results" not in payload  # Raw Response 미전달
    assert set(payload) >= {"headline", "reference_only", "focus"}


def test_template_brief_passes_guardrails(payload):
    b = TemplateInsightProvider().generate(payload)
    assert violations(b, payload) == []
    assert REQUIRED_DISCLAIMER in b.interpretation
    assert len(b.validation_questions) == 1 and len(b.deep_dive_questions) == 1
    assert "암보험" in b.what_changed and "검색 관심지수" in b.what_changed


def test_template_questions_come_from_focus_topic(payload, topics):
    b = TemplateInsightProvider().generate(payload)
    focus = topics.by_display_name(payload["focus"]["name"])
    assert b.validation_questions == [focus.validation_question]
    assert b.deep_dive_questions == [focus.deep_dive_question]


def test_template_excludes_cautioned_topic(payload):
    b = TemplateInsightProvider().generate(payload)
    # 건강보험은 caution Topic: 수치를 인용하지 않고 '제외했다'고만 언급
    assert "건강보험(3개월" not in b.what_changed and "제외" in b.what_changed


def test_template_with_no_data():
    p = {"segment": {"label": "X"}, "topics": [{"name": "A", "direction": "UNKNOWN", "three_month_momentum_pct": None}]}
    b = TemplateInsightProvider().generate(p)
    assert violations(b, p) == []


def test_template_without_up_signal_uses_generic_questions():
    p = {
        "segment": {"label": "X"}, "focus": None,
        "topics": [{"name": "A", "direction": "DOWN", "three_month_momentum_pct": -9.0, "mom_pct": -1.0}],
    }
    b = TemplateInsightProvider().generate(p)
    assert violations(b, p) == [] and b.validation_questions and b.deep_dive_questions
    assert "필요가 줄었다는 뜻은 아니" in b.interpretation


@pytest.mark.parametrize(
    "phrase", ["반드시 가입", "이 상품을 추천", "판매해야", "가입해야 한다", "가장 좋은 보험", "암보험 검색량이 18% 증가했다", "암보험 판매가 증가하고 있다"]
)
def test_guardrails_reject_forbidden(phrase):
    assert violations(mk(what=phrase))
    assert violations(mk(interp=f"{phrase}. {REQUIRED_DISCLAIMER}"))


@pytest.mark.parametrize(
    "phrase",
    ["암 진단 소식 때문에 관심이 늘었습니다", "이 고객군에는 암보험이 필요합니다", "고객 니즈가 높습니다", "질병 위험이 높아졌습니다"],
)
def test_guardrails_reject_unsupported_claims(phrase):
    assert violations(mk(what=phrase))


def test_guardrails_require_disclaimer_in_interpretation_and_questions():
    assert violations(mk(interp="암보험 관심지수가 올랐습니다."))
    assert violations(mk(v=()))
    assert violations(mk(d=()))
    assert violations(mk(v=("a", "b", "c")))
    assert violations(mk(d=("a", "b", "c")))
    assert violations(mk(what="", interp=REQUIRED_DISCLAIMER))


def test_guardrails_reject_numbers_not_in_payload(payload):
    ok_val = payload["topics"][0]["three_month_momentum_pct"]
    assert violations(mk(what=f"암보험이 평균 대비 {ok_val:+.1f}% 높습니다."), payload) == []
    assert any("수치" in v for v in violations(mk(what="암보험이 평균 대비 +42.7% 높습니다."), payload))


def llm(handler):
    return OpenAIInsightProvider("k", client=httpx.Client(transport=httpx.MockTransport(handler)))


def chat(content: dict):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]})


def good_llm(payload):
    pct = payload["topics"][0]["three_month_momentum_pct"]
    return {
        "what_changed": f"암보험 검색 관심지수가 3개월 평균 대비 {pct:+.1f}%로 높게 나타났습니다.",
        "interpretation": f"특정 보장 영역의 관심 변화를 탐색할 Signal입니다. {REQUIRED_DISCLAIMER}",
        "validation_questions": ["걱정되는 부분이 있으신가요?"],
        "deep_dive_questions": ["치료비와 소득 공백 중 어느 쪽이 걱정되시나요?"],
    }


def test_llm_good_output_used(payload):
    b = llm(lambda r: chat(good_llm(payload))).generate(payload)
    assert b.provider == "openai" and b.note is None


def test_llm_prompt_contains_rules_and_only_metrics(payload):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return chat(good_llm(payload))

    llm(handler).generate(payload)
    system, user = seen["messages"][0]["content"], seen["messages"][1]["content"]
    assert REQUIRED_DISCLAIMER in system and "추천" in system and "때문에" in system
    assert json.loads(user) == payload
    assert "current_index" not in user


def test_llm_forbidden_output_falls_back(payload):
    bad = {**good_llm(payload), "interpretation": f"이 상품을 추천합니다. {REQUIRED_DISCLAIMER}"}
    b = llm(lambda r: chat(bad)).generate(payload)
    assert b.provider == "template" and b.note and violations(b, payload) == []


def test_llm_invented_number_falls_back(payload):
    bad = {**good_llm(payload), "what_changed": "암보험이 평균 대비 +99.9% 높습니다."}
    b = llm(lambda r: chat(bad)).generate(payload)
    assert b.provider == "template" and b.note


@pytest.mark.parametrize("resp", [httpx.Response(500), httpx.Response(200, json={"x": 1}), httpx.Response(200, content=b"no")])
def test_llm_failure_falls_back(payload, resp):
    b = llm(lambda r: resp).generate(payload)
    assert b.provider == "template" and b.note


def test_provider_selection(cfg, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(get_provider(cfg), TemplateInsightProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert isinstance(get_provider(cfg), OpenAIInsightProvider)


def test_template_notes_broad_move():
    p = {
        "segment": {"label": "X"}, "focus": None, "broad_move": "DOWN",
        "topics": [{"name": "A", "direction": "DOWN", "three_month_momentum_pct": -9.0, "mom_pct": -1.0}],
    }
    b = TemplateInsightProvider().generate(p)
    assert "함께 움직였" in b.interpretation and violations(b, p) == []
