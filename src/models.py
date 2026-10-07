"""Raw / Normalized / Metric schema 정의."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Naver DataLab 공식 연령 코드 (ages 파라미터). docs/DATA_METHODOLOGY.md §1.3
AGE_CODES: dict[str, str] = {
    "3": "19~24",
    "4": "25~29",
    "5": "30~34",
    "6": "35~39",
    "7": "40~44",
    "8": "45~49",
    "9": "50~54",
    "10": "55~59",
    "11": "60+",
}

# UI 성별 -> Naver gender 파라미터 (전체는 파라미터 생략)
GENDERS: dict[str, tuple[str, Optional[str]]] = {
    "male": ("남성", "m"),
    "female": ("여성", "f"),
    "all": ("전체", None),
}


class Direction(str, Enum):
    UP = "UP"
    STABLE = "STABLE"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"  # 데이터 부족/계산 불가


class Segment(BaseModel):
    age_code: str
    gender: str  # male | female | all

    @property
    def age_label(self) -> str:
        return AGE_CODES[self.age_code]

    @property
    def gender_label(self) -> str:
        return GENDERS[self.gender][0]

    @property
    def label(self) -> str:
        suffix = "" if self.age_label == "60+" else "세"
        age = "60세 이상" if self.age_label == "60+" else f"{self.age_label}{suffix}"
        return f"{age} {self.gender_label}"

    @property
    def key(self) -> str:
        return f"{self.age_label.replace('~', '-').replace('+', 'plus')}_{self.gender}"


class RequestMeta(BaseModel):
    """Raw 저장 시 함께 남기는 조회 조건 (이게 없으면 ratio를 해석할 수 없다)."""

    requested_at: datetime
    start_date: date
    end_date: date
    time_unit: str = "month"
    age_codes: list[str]
    gender: Optional[str] = None
    device: Optional[str] = None
    topics_version: str
    topic_groups: dict[str, list[str]]  # groupName -> keywords
    source: str = "NAVER_DATALAB_SEARCH"


class NormalizedRecord(BaseModel):
    period: date
    age_group: str
    gender: str
    topic: str  # topic id (예: cancer)
    ratio: float


class TopicMetric(BaseModel):
    """project-defined metric (Naver 공식 지표 아님)."""

    topic: str
    display_name: str
    current_period: Optional[date] = None
    current_index: Optional[float] = None
    mom_pct: Optional[float] = None
    three_month_avg: Optional[float] = None
    momentum_pct: Optional[float] = None
    direction: Direction = Direction.UNKNOWN
    n_points: int = 0
    rises: Optional[int] = None  # 최근 persistence_months 개 MoM 중 상승 횟수
    rise_window: Optional[int] = None  # 위 판정에 쓴 MoM 관측 수 (연속 월만)
    note: Optional[str] = None  # 계산 불가 사유 등


class SegmentReport(BaseModel):
    segment: Segment
    data_source: str  # "mock" | "real"
    meta: Optional[RequestMeta] = None
    from_cache: bool = False
    records: list[NormalizedRecord] = Field(default_factory=list)
    metrics: list[TopicMetric] = Field(default_factory=list)
    error: Optional[str] = None  # 사용자에게 보여줄 친화적 메시지
