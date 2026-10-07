"""이번 달 주목 Signal / FC Check Point / 상담 질문 선정. 새 수치를 만들지 않고 계산된 TopicMetric 만 선택·정렬한다.

시장 Signal -> 니즈 가설 -> FC 질문 -> 고객 검증 중 앞의 두 단계만 지원한다. 니즈를 판단하지 않는다.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.config import TopicsConfig
from src.models import Direction, SegmentReport, TopicMetric


class Signal(BaseModel):
    topic: str  # display_name
    direction: Direction
    momentum_pct: Optional[float] = None
    mom_pct: Optional[float] = None
    rises: Optional[int] = None
    rise_window: Optional[int] = None
    caution: Optional[str] = None


BROAD_MOVE_MIN = 3  # 이 수 이상의 Topic 이 같은 방향이면 특정 영역이 아닌 '전반적 움직임'으로 본다


class ConsultPrep(BaseModel):
    headline: list[Signal] = Field(default_factory=list)  # 방향이 있는 주목 Signal (|Momentum| 큰 순)
    stable_topics: list[str] = Field(default_factory=list)  # 큰 변화 없는 Topic
    reference: list[Signal] = Field(default_factory=list)  # 데이터 품질 경고로 헤드라인에서 제외한 Topic
    unknown_topics: list[str] = Field(default_factory=list)
    broad_move: Optional[Direction] = None  # 여러 Topic 이 같은 방향으로 함께 움직인 경우
    focus: Optional[Signal] = None  # 질문의 기준이 되는 Signal (UP 우선)
    check_point: Optional[str] = None
    validation_question: Optional[str] = None
    deep_dive_question: Optional[str] = None


def _signal(m: TopicMetric, caution: Optional[str]) -> Signal:
    return Signal(
        topic=m.display_name, direction=m.direction, momentum_pct=m.momentum_pct, mom_pct=m.mom_pct,
        rises=m.rises, rise_window=m.rise_window, caution=caution,
    )


def build_consult_prep(report: SegmentReport, topics: TopicsConfig) -> ConsultPrep:
    prep = ConsultPrep()
    movers: list[Signal] = []
    for m in report.metrics:
        topic = topics.by_display_name(m.display_name)
        caution = topic.caution if topic else None
        sig = _signal(m, caution)
        if m.direction == Direction.UNKNOWN:
            prep.unknown_topics.append(m.display_name)
        elif caution:
            prep.reference.append(sig)
        elif m.direction == Direction.STABLE:
            prep.stable_topics.append(m.display_name)
        else:
            movers.append(sig)

    movers.sort(key=lambda s: abs(s.momentum_pct or 0), reverse=True)
    prep.headline = movers
    for d in (Direction.UP, Direction.DOWN):
        if sum(1 for sg in movers if sg.direction == d) >= BROAD_MOVE_MIN:
            prep.broad_move = d

    # 질문 기준: 관심이 오른 Topic 우선. 오른 Topic 이 없으면 질문을 Market Signal 에 억지로 묶지 않는다.
    focus = next((s for s in prep.headline if s.direction == Direction.UP), None)
    if focus:
        prep.focus = focus
        topic = topics.by_display_name(focus.topic)
        if topic:
            prep.check_point = topic.check_point
            prep.validation_question = topic.validation_question
            prep.deep_dive_question = topic.deep_dive_question
    return prep
