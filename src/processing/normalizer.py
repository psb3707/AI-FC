"""Naver DataLab Raw Response -> NormalizedRecord. Raw 는 수정하지 않는다."""
from __future__ import annotations

from datetime import date
from typing import Any

from src.config import TopicsConfig
from src.models import AGE_CODES, GENDERS, NormalizedRecord


class MalformedResponseError(ValueError):
    pass


def normalize(raw: Any, topics: TopicsConfig, age_code: str, gender: str) -> list[NormalizedRecord]:
    """응답의 results[].title(= groupName) 을 topics 설정의 display_name 으로 매핑한다.

    - 구조가 깨졌으면 MalformedResponseError
    - results 가 비어 있으면 빈 리스트 (호출부에서 '데이터 없음' 처리)
    - 알 수 없는 title 은 무시, 개별 data 항목이 깨졌으면 해당 항목만 건너뜀
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        raise MalformedResponseError("응답에 results 배열이 없습니다")
    age_label = AGE_CODES.get(age_code, age_code)
    gender_key = gender if gender in GENDERS else "all"
    out: list[NormalizedRecord] = []
    for res in raw["results"]:
        if not isinstance(res, dict) or not isinstance(res.get("data"), list):
            raise MalformedResponseError("results 항목 구조가 올바르지 않습니다")
        topic = topics.by_display_name(str(res.get("title", "")))
        if topic is None:
            continue
        for item in res["data"]:
            try:
                period = date.fromisoformat(str(item["period"])[:10])
                ratio = float(item["ratio"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append(
                NormalizedRecord(period=period, age_group=age_label, gender=gender_key, topic=topic.id, ratio=ratio)
            )
    out.sort(key=lambda r: (r.topic, r.period))
    return out
