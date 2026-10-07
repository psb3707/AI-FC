"""Insight Provider 인터페이스. LLM Provider 는 이 인터페이스 뒤로 분리한다."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from src.config import TopicsConfig
from src.insights.signals import build_consult_prep
from src.models import SegmentReport

REQUIRED_DISCLAIMER = (
    "검색 관심도는 실제 판매량이나 개인 고객의 보험 필요성을 의미하지 않습니다."
)
GENERIC_VALIDATION_QUESTION = "최근 보험이나 보장과 관련해 새롭게 신경 쓰이는 부분이 있으신가요?"
GENERIC_DEEP_DIVE_QUESTION = "지금 가장 걱정되는 위험은 치료비, 소득 중단, 가족 부담 중 어느 쪽에 가까우신가요?"


class Brief(BaseModel):
    """Fact -> Interpretation -> Action 구조. 새 수치/원인/상품 추천을 담지 않는다."""

    what_changed: str  # [1] 데이터로 확인된 사실
    interpretation: str  # [2] 상담 준비 관점의 해석 (면책 문구 포함)
    validation_questions: list[str] = Field(default_factory=list)  # [3-A] Signal Validation (최대 2)
    deep_dive_questions: list[str] = Field(default_factory=list)  # [3-B] Need Deep-Dive (최대 2)
    provider: str = "template"  # template | openai
    note: Optional[str] = None  # 예: LLM 실패로 규칙 기반으로 대체

    @property
    def questions(self) -> list[str]:
        return self.validation_questions + self.deep_dive_questions

    @property
    def text(self) -> str:
        return self.what_changed + "\n" + self.interpretation


class InsightProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, payload: dict) -> Brief:
        """payload 는 Python 이 계산한 구조화 지표(build_payload). 새 수치를 만들지 않는다."""


def build_payload(report: SegmentReport, topics: Optional[TopicsConfig] = None) -> dict:
    """LLM/템플릿에 전달하는 유일한 입력. Raw Response·Raw 관심지수는 전달하지 않는다 (Topic 간 크기 비교 방지)."""
    period = report.metrics[0].current_period if report.metrics else None
    payload = {
        "segment": {"age": report.segment.age_label, "gender": report.segment.gender_label, "label": report.segment.label},
        "period": period.strftime("%Y-%m") if period else None,
        "topics": [
            {
                "name": m.display_name,
                "mom_pct": m.mom_pct,
                "three_month_momentum_pct": m.momentum_pct,
                "direction": m.direction.value,
            }
            for m in report.metrics
        ],
    }
    if topics is not None:
        prep = build_consult_prep(report, topics)
        payload["broad_move"] = prep.broad_move.value if prep.broad_move else None  # 여러 Topic 이 같은 방향
        payload["headline"] = [s.topic for s in prep.headline]  # 방향이 있는 주목 Signal (|Momentum| 큰 순)
        payload["reference_only"] = [  # 데이터 품질 경고로 해석에서 제외할 Topic
            {"name": s.topic, "caution": s.caution} for s in prep.reference
        ]
        payload["focus"] = (
            {
                "name": prep.focus.topic,
                "check_point": prep.check_point,
                "validation_question": prep.validation_question,
                "deep_dive_question": prep.deep_dive_question,
            }
            if prep.focus else None
        )
    return payload
