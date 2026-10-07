"""Naver DataLab 통합 검색어 트렌드 API Collector.

책임: Request 생성 / 인증 헤더 / 호출 / HTTP 오류 처리 / Raw Response 반환.
Trend 계산은 하지 않는다. Raw 저장은 storage.repository 가 담당한다.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx

from src.config import CollectorConfig
from src.models import RequestMeta

log = logging.getLogger(__name__)

ENDPOINT = "https://openapi.naver.com/v1/datalab/search"
MIN_START_DATE = date(2016, 1, 1)  # 공식 조회 가능 최초 일자

_USER_MESSAGES = {
    400: "요청 형식이 올바르지 않습니다. (조회 조건 또는 Keyword 설정을 확인해 주세요)",
    401: "네이버 API 인증에 실패했습니다. NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 확인해 주세요.",
    403: "네이버 API 권한이 없습니다. 개발자센터 Application 에 '데이터랩 (검색어트렌드)' API 가 추가되어 있는지 확인해 주세요.",
    429: "네이버 API 호출 한도(일 1,000회)를 초과했거나 요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
}


class CollectorError(Exception):
    def __init__(self, user_message: str, status_code: Optional[int] = None, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code
        self.detail = detail


class RawResult:
    """원본 응답(수정 금지)과 조회 조건 Metadata."""

    def __init__(self, response: dict[str, Any], meta: RequestMeta):
        self.response = response
        self.meta = meta


class NaverDataLabCollector:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        config: Optional[CollectorConfig] = None,
        client: Optional[httpx.Client] = None,
        sleep=time.sleep,
    ):
        if not client_id or not client_secret:
            raise CollectorError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 설정되지 않았습니다. .env 를 확인해 주세요.")
        self._cfg = config or CollectorConfig()
        self._headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
        }
        self._client = client or httpx.Client(timeout=self._cfg.timeout_seconds)
        self._sleep = sleep
        self._last_call = 0.0

    @staticmethod
    def build_body(
        start_date: date,
        end_date: date,
        time_unit: str,
        keyword_groups: list[dict],
        age_code: Optional[str] = None,
        gender: Optional[str] = None,  # 'm' | 'f' | None(전체: 파라미터 생략)
        device: Optional[str] = None,  # 'pc' | 'mo' | None(전체: 생략)
    ) -> dict[str, Any]:
        if start_date < MIN_START_DATE:
            raise CollectorError(f"조회 시작일은 {MIN_START_DATE} 이후여야 합니다.")
        if end_date < start_date:
            raise CollectorError("조회 종료일이 시작일보다 빠릅니다.")
        if time_unit not in ("date", "week", "month"):
            raise CollectorError(f"지원하지 않는 timeUnit: {time_unit}")
        if not 1 <= len(keyword_groups) <= 5:
            raise CollectorError("keywordGroups 는 1~5개여야 합니다.")
        body: dict[str, Any] = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
        }
        if gender:
            body["gender"] = gender
        if age_code:
            body["ages"] = [age_code]  # 원칙: 1 Segment = 1 Age Code
        if device:
            body["device"] = device
        return body

    def _throttle(self) -> None:
        wait = self._cfg.min_interval_seconds - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def fetch_trends(
        self,
        start_date: date,
        end_date: date,
        time_unit: str,
        keyword_groups: list[dict],
        age_code: Optional[str] = None,
        gender: Optional[str] = None,
        device: Optional[str] = None,
        topics_version: str = "unknown",
    ) -> RawResult:
        body = self.build_body(start_date, end_date, time_unit, keyword_groups, age_code, gender, device)
        meta = RequestMeta(
            requested_at=datetime.now(timezone.utc),
            start_date=start_date,
            end_date=end_date,
            time_unit=time_unit,
            age_codes=[age_code] if age_code else [],
            gender=gender,
            device=device,
            topics_version=topics_version,
            topic_groups={g["groupName"]: list(g["keywords"]) for g in keyword_groups},
        )
        attempts = max(1, self._cfg.max_retries)
        last_err: Optional[CollectorError] = None
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                resp = self._client.post(ENDPOINT, headers=self._headers, json=body)
            except httpx.TimeoutException as e:
                last_err = CollectorError("네이버 API 응답 시간이 초과되었습니다.", detail=str(e))
                log.warning("naver timeout (attempt %s/%s)", attempt, attempts)
            except httpx.HTTPError as e:
                last_err = CollectorError("네이버 API 에 연결할 수 없습니다. 네트워크를 확인해 주세요.", detail=str(e))
                log.warning("naver network error (attempt %s/%s): %s", attempt, attempts, e)
            else:
                if resp.status_code == 200:
                    return RawResult(self._parse_json(resp), meta)
                msg = _USER_MESSAGES.get(resp.status_code, f"네이버 API 오류가 발생했습니다. (HTTP {resp.status_code})")
                last_err = CollectorError(msg, resp.status_code, resp.text[:300])
                log.warning("naver http %s (attempt %s/%s)", resp.status_code, attempt, attempts)
                if resp.status_code < 500 and resp.status_code != 429:
                    raise last_err  # 4xx(429 제외)는 재시도해도 소용없다
            if attempt < attempts:
                self._sleep(self._cfg.backoff_seconds * 2 ** (attempt - 1))
        assert last_err is not None
        raise last_err

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as e:
            raise CollectorError("네이버 API 응답을 해석할 수 없습니다.", resp.status_code, resp.text[:300]) from e
        if not isinstance(data, dict) or "results" not in data:
            raise CollectorError("네이버 API 응답 형식이 예상과 다릅니다.", resp.status_code, str(data)[:300])
        return data
