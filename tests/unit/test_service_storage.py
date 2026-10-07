import json
from datetime import date

import httpx
import pytest

from src.collectors.naver_datalab import NaverDataLabCollector
from src.config import AppConfig, CollectorConfig
from src.models import Direction, Segment
from src.service import ReportService, window
from src.storage.repository import Repository

TODAY = date(2026, 10, 7)
SEG = Segment(age_code="4", gender="male")


def test_window_uses_complete_months():
    assert window(12, TODAY) == (date(2025, 10, 1), date(2026, 9, 30))
    assert window(6, TODAY) == (date(2026, 4, 1), date(2026, 9, 30))
    assert window(12, date(2026, 1, 15)) == (date(2025, 1, 1), date(2025, 12, 31))


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "c.sqlite3", tmp_path / "raw")


def test_mock_mode_end_to_end(topics, cfg, repo):
    svc = ReportService("mock", topics, cfg, repo)
    r = svc.get_report(SEG, 12, TODAY)
    assert r.error is None and r.data_source == "mock" and r.meta.source == "MOCK_DEMO"
    assert len(r.metrics) == 5 and all(m.n_points == 12 for m in r.metrics)
    assert max(rec.ratio for rec in r.records) == pytest.approx(100, abs=0.01)
    again = svc.get_report(SEG, 12, TODAY)
    assert [m.current_index for m in again.metrics] == [m.current_index for m in r.metrics]  # 결정적
    other = svc.get_report(Segment(age_code="7", gender="female"), 12, TODAY)
    assert [m.current_index for m in other.metrics] != [m.current_index for m in r.metrics]


def test_mock_does_not_write_raw_or_cache(topics, cfg, repo, tmp_path):
    ReportService("mock", topics, cfg, repo).get_report(SEG, 12, TODAY)
    assert not (tmp_path / "raw").exists()


def real_service(topics, cfg, repo, handler):
    col = NaverDataLabCollector(
        "i", "s", CollectorConfig(backoff_seconds=0, min_interval_seconds=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None,
    )
    return ReportService("real", topics, cfg, repo, col)


def test_real_mode_saves_raw_and_caches(topics, cfg, repo, naver_response, tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=naver_response)

    svc = real_service(topics, cfg, repo, handler)
    r1 = svc.get_report(SEG, 12, TODAY)
    assert r1.error is None and not r1.from_cache and r1.data_source == "real"
    assert next(m for m in r1.metrics if m.topic == "cancer").direction == Direction.UP
    files = list((tmp_path / "raw" / "naver").rglob("age_4_gender_m_12m.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["response"] == naver_response  # Raw 원본 보존
    assert saved["metadata"]["age_codes"] == ["4"] and saved["metadata"]["topics_version"] == "v1"
    assert set(saved["metadata"]) >= {"requested_at", "start_date", "end_date", "time_unit", "gender", "topic_groups", "source"}

    r2 = svc.get_report(SEG, 12, TODAY)
    assert r2.from_cache and len(calls) == 1  # 재호출 없음
    svc.get_report(Segment(age_code="4", gender="female"), 12, TODAY)
    assert len(calls) == 2  # 다른 Segment 는 별도 호출


def test_cache_ttl_expired(topics, repo, naver_response):
    cfg = AppConfig(cache={"ttl_hours": 0})
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=naver_response)

    svc = real_service(topics, cfg, repo, handler)
    svc.get_report(SEG, 12, TODAY)
    svc.get_report(SEG, 12, TODAY)
    assert len(calls) == 2


def test_api_error_becomes_friendly_message(topics, cfg, repo):
    svc = real_service(topics, cfg, repo, lambda req: httpx.Response(403, text="forbidden"))
    r = svc.get_report(SEG, 12, TODAY)
    assert r.error and "데이터랩" in r.error and r.metrics == []


def test_malformed_response_does_not_crash(topics, cfg, repo):
    svc = real_service(topics, cfg, repo, lambda req: httpx.Response(200, json={"results": [1]}))
    r = svc.get_report(SEG, 12, TODAY)
    assert r.error


def test_empty_results_reported(topics, cfg, repo):
    svc = real_service(topics, cfg, repo, lambda req: httpx.Response(200, json={"results": []}))
    assert "데이터가 없습니다" in svc.get_report(SEG, 12, TODAY).error


def test_real_mode_without_keys(topics, cfg, repo, monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    r = ReportService.from_env("real", topics, cfg, repo).get_report(SEG, 12, TODAY)
    assert r.error and "NAVER_CLIENT_ID" in r.error
