import json
from datetime import date

import httpx
import pytest

from src.collectors.naver_datalab import ENDPOINT, CollectorError, NaverDataLabCollector
from src.config import CollectorConfig

CFG = CollectorConfig(max_retries=3, backoff_seconds=0, min_interval_seconds=0)
GROUPS = [{"groupName": "암보험", "keywords": ["암보험"]}]


def make(handler, cfg=CFG):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NaverDataLabCollector("id", "secret", cfg, client=client, sleep=lambda s: None)


def fetch(c, **kw):
    return c.fetch_trends(date(2025, 10, 1), date(2026, 9, 30), "month", GROUPS, age_code="4", gender="m", **kw)


def test_success_sends_correct_request(naver_response):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json=naver_response)

    r = fetch(make(handler), topics_version="v1")
    assert seen["url"] == ENDPOINT
    assert seen["headers"]["x-naver-client-id"] == "id" and seen["headers"]["x-naver-client-secret"] == "secret"
    assert seen["body"]["ages"] == ["4"] and seen["body"]["gender"] == "m" and seen["body"]["timeUnit"] == "month"
    assert "device" not in seen["body"]
    assert r.response == naver_response  # Raw 미수정
    assert r.meta.topics_version == "v1" and r.meta.age_codes == ["4"]


def test_gender_all_omits_parameter():
    body = NaverDataLabCollector.build_body(date(2026, 1, 1), date(2026, 2, 28), "month", GROUPS, "4", None)
    assert "gender" not in body


@pytest.mark.parametrize("status", [400, 401, 403])
def test_client_errors_not_retried(status):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(status, text="err")

    with pytest.raises(CollectorError) as e:
        fetch(make(handler))
    assert len(calls) == 1 and e.value.status_code == status
    if status == 403:
        assert "데이터랩" in e.value.user_message


def test_server_error_retried_then_fails():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(CollectorError) as e:
        fetch(make(handler))
    assert len(calls) == 3 and e.value.status_code == 500  # 무한 재시도 금지


def test_retry_then_success(naver_response):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 2 else httpx.Response(200, json=naver_response)

    assert fetch(make(handler)).response == naver_response and len(calls) == 2


def test_timeout_handled():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(CollectorError) as e:
        fetch(make(handler))
    assert "시간" in e.value.user_message


@pytest.mark.parametrize("content", [b"<html>", b"[]", b'{"foo": 1}'])
def test_invalid_response(content):
    with pytest.raises(CollectorError):
        fetch(make(lambda req: httpx.Response(200, content=content)))


def test_missing_credentials():
    with pytest.raises(CollectorError):
        NaverDataLabCollector("", "")


def test_request_validation():
    with pytest.raises(CollectorError):
        NaverDataLabCollector.build_body(date(2015, 1, 1), date(2016, 1, 1), "month", GROUPS)
    with pytest.raises(CollectorError):
        NaverDataLabCollector.build_body(date(2026, 1, 1), date(2026, 2, 1), "year", GROUPS)
    with pytest.raises(CollectorError):
        NaverDataLabCollector.build_body(date(2026, 1, 1), date(2026, 2, 1), "month", GROUPS * 6)
