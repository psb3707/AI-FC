"""Insight Provider 인터페이스. LLM Provider 는 이 인터페이스 뒤로 분리한다."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from src.models import SegmentReport

REQUIRED_DISCLAIMER = (
    "검색 관심도는 실제 판매량이나 개인 고객의 보험 필요성을 의미하지 않습니다."
)


class Brief(BaseModel):
    summary: str
    questions: list[str] = Field(default_factory=list)  # 최대 3개, Needs Discovery 질문
    provider: str = "template"  # template | openai
    note: Optional[str] = None  # 예: LLM 실패로 규칙 기반으로 대체


class InsightProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, payload: dict) -> Brief:
        """payload 는 Python 이 계산한 구조화 지표(build_payload). 새 수치를 만들지 않는다."""


def build_payload(report: SegmentReport) -> dict:
    """LLM/템플릿에 전달하는 유일한 입력. Raw Response 는 전달하지 않는다."""
    period = report.metrics[0].current_period if report.metrics else None
    return {
        "segment": {"age": report.segment.age_label, "gender": report.segment.gender_label, "label": report.segment.label},
        "period": period.strftime("%Y-%m") if period else None,
        "topics": [
            {
                "name": m.display_name,
                "current_index": m.current_index,
                "mom_pct": m.mom_pct,
                "three_month_momentum_pct": m.momentum_pct,
                "direction": m.direction.value,
            }
            for m in report.metrics
        ],
    }
