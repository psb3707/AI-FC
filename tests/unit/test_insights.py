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
    return build_payload(rep)


def test_payload_has_only_computed_metrics(payload):
    assert payload["segment"]["label"] == "25~29세 남성" and payload["period"] == "2026-09"
    t = payload["topics"][0]
    assert set(t) == {"name", "current_index", "mom_pct", "three_month_momentum_pct", "direction"}
    assert "results" not in payload  # Raw Response 미전달


def test_template_brief_passes_guardrails(payload):
    b = TemplateInsightProvider().generate(payload)
    assert violations(b) == []
    assert REQUIRED_DISCLAIMER in b.summary
    assert 1 <= len(b.questions) <= 3
    assert "암보험" in b.summary and "검색 관심지수" in b.summary


def test_template_with_no_data():
    p = {"segment": {"label": "X"}, "topics": [{"name": "A", "direction": "UNKNOWN", "three_month_momentum_pct": None}]}
    b = TemplateInsightProvider().generate(p)
    assert violations(b) == []


@pytest.mark.parametrize(
    "phrase", ["반드시 가입", "이 상품을 추천", "판매해야", "가입해야 한다", "가장 좋은 보험", "암보험 검색량이 18% 증가했다", "암보험 판매가 증가하고 있다"]
)
def test_guardrails_reject_forbidden(phrase):
    b = Brief(summary=f"{phrase}. {REQUIRED_DISCLAIMER}", questions=["q"])
    assert violations(b)


def test_guardrails_require_disclaimer_and_questions():
    assert violations(Brief(summary="암보험 관심지수가 올랐습니다.", questions=["q"]))
    assert violations(Brief(summary=REQUIRED_DISCLAIMER, questions=[]))
    assert violations(Brief(summary=REQUIRED_DISCLAIMER, questions=list("abcd")))


def llm(handler):
    return OpenAIInsightProvider("k", client=httpx.Client(transport=httpx.MockTransport(handler)))


def chat(content: dict):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]})


def test_llm_good_output_used(payload):
    good = {"summary": f"암보험 검색 관심지수가 상승했습니다. {REQUIRED_DISCLAIMER}", "questions": ["걱정되는 위험이 있으신가요?"]}
    b = llm(lambda r: chat(good)).generate(payload)
    assert b.provider == "openai" and b.note is None


def test_llm_prompt_contains_rules_and_only_metrics(payload):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return chat({"summary": REQUIRED_DISCLAIMER, "questions": ["q"]})

    llm(handler).generate(payload)
    system, user = seen["messages"][0]["content"], seen["messages"][1]["content"]
    assert REQUIRED_DISCLAIMER in system and "추천" in system
    assert json.loads(user) == payload


def test_llm_forbidden_output_falls_back(payload):
    bad = {"summary": f"이 상품을 추천합니다. {REQUIRED_DISCLAIMER}", "questions": ["q"]}
    b = llm(lambda r: chat(bad)).generate(payload)
    assert b.provider == "template" and b.note and violations(b) == []


@pytest.mark.parametrize("resp", [httpx.Response(500), httpx.Response(200, json={"x": 1}), httpx.Response(200, content=b"no")])
def test_llm_failure_falls_back(payload, resp):
    b = llm(lambda r: resp).generate(payload)
    assert b.provider == "template" and b.note


def test_provider_selection(cfg, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(get_provider(cfg), TemplateInsightProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert isinstance(get_provider(cfg), OpenAIInsightProvider)
