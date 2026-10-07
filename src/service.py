"""조회 오케스트레이션: Collector/Mock -> Raw 저장·캐시 -> Normalizer -> Trend. 예외는 SegmentReport.error 로 변환."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.collectors.mock_data import build_mock_response
from src.collectors.naver_datalab import CollectorError, NaverDataLabCollector
from src.config import AppConfig, TopicsConfig
from src.models import GENDERS, RequestMeta, Segment, SegmentReport
from src.processing.normalizer import MalformedResponseError, normalize
from src.processing.trend_calculator import compute_metrics
from src.storage.repository import Repository

log = logging.getLogger(__name__)


def window(months: int, today: Optional[date] = None) -> tuple[date, date]:
    """완결된 월만 사용: end = 직전 월 말일, start = end 월에서 (months-1)개월 전 1일."""
    today = today or date.today()
    end = today.replace(day=1) - timedelta(days=1)
    idx = end.year * 12 + end.month - 1 - (months - 1)
    return date(idx // 12, idx % 12 + 1, 1), end


class ReportService:
    def __init__(self, mode: str, topics: TopicsConfig, cfg: AppConfig, repo: Repository, collector: Optional[NaverDataLabCollector] = None):
        self.mode, self.topics, self.cfg, self.repo, self.collector = mode, topics, cfg, repo, collector
        self.collector_error: Optional[str] = None  # from_env 에서 Collector 생성 실패 사유

    @classmethod
    def from_env(cls, mode: str, topics: TopicsConfig, cfg: AppConfig, repo: Repository) -> "ReportService":
        collector, error = None, None
        if mode == "real":
            try:
                collector = NaverDataLabCollector(
                    os.getenv("NAVER_CLIENT_ID", ""), os.getenv("NAVER_CLIENT_SECRET", ""), cfg.collector,
                    provider=os.getenv("NAVER_API_PROVIDER", "developers").strip().lower() or "developers",
                )
            except CollectorError as e:
                error = e.user_message  # get_report 에서 친화적 오류로 안내
        svc = cls(mode, topics, cfg, repo, collector)
        svc.collector_error = error
        return svc

    def get_report(self, segment: Segment, months: int, today: Optional[date] = None) -> SegmentReport:
        start, end = window(months, today)
        gender_param = GENDERS[segment.gender][1]
        report = SegmentReport(segment=segment, data_source=self.mode)
        try:
            if self.mode == "mock":
                meta = RequestMeta(
                    requested_at=datetime.now(timezone.utc), start_date=start, end_date=end,
                    age_codes=[segment.age_code], gender=gender_param, topics_version=self.topics.topics_version,
                    topic_groups={g["groupName"]: g["keywords"] for g in self.topics.keyword_groups},
                    source="MOCK_DEMO",
                )
                response = build_mock_response(meta)
            else:
                if self.collector is None:
                    report.error = self.collector_error or "실데이터 모드입니다. .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 설정하거나 APP_MODE=mock 으로 실행해 주세요."
                    return report
                probe = RequestMeta(
                    requested_at=datetime.now(timezone.utc), start_date=start, end_date=end,
                    age_codes=[segment.age_code], gender=gender_param, topics_version=self.topics.topics_version,
                    topic_groups={g["groupName"]: g["keywords"] for g in self.topics.keyword_groups},
                    source=self.collector.source,  # 캐시 키 일치 (fetch 시 저장되는 meta.source 와 동일해야 함)
                )
                cached = self.repo.get_cache(probe, self.cfg.cache.ttl_hours)
                if cached:
                    meta, response = cached
                    report.from_cache = True
                else:
                    raw = self.collector.fetch_trends(
                        start, end, "month", self.topics.keyword_groups,
                        age_code=segment.age_code, gender=gender_param, topics_version=self.topics.topics_version,
                    )
                    meta, response = raw.meta, raw.response
                    self.repo.save_raw(meta, response)
                    self.repo.put_cache(meta, response)
            report.meta = meta
            report.records = normalize(response, self.topics, segment.age_code, segment.gender)
            if not report.records:
                report.error = "해당 조건에서 조회된 데이터가 없습니다."
                return report
            report.metrics = compute_metrics(report.records, self.topics, self.cfg.trend)
        except CollectorError as e:
            log.error("collector error: %s | %s", e.user_message, e.detail)
            report.error = e.user_message
        except MalformedResponseError as e:
            log.error("malformed response: %s", e)
            report.error = "네이버 API 응답 형식이 예상과 달라 데이터를 표시할 수 없습니다."
        except Exception:  # 대시보드 전체가 죽지 않도록 마지막 방어선
            log.exception("unexpected error")
            report.error = "예기치 못한 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        return report
