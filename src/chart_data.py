"""Trend Chart 용 데이터 구성. 수치는 계산하지 않고 TopicMetric(trend_calculator 결과)과 기록을 표시용으로 정리만 한다."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from src.models import NormalizedRecord, TopicMetric


def _mi(d: date) -> int:
    return d.year * 12 + d.month


def topic_chart_frame(records: list[NormalizedRecord], topic_id: str, metric: TopicMetric, baseline_months: int) -> pd.DataFrame:
    """period / ratio / role(baseline|current|other). 3M Average 가 계산된 경우에만 baseline 구간을 표시한다."""
    rows = sorted(((r.period, r.ratio) for r in records if r.topic == topic_id), key=lambda x: x[0])
    cur: Optional[date] = metric.current_period
    has_base = metric.three_month_avg is not None and cur is not None

    def role(p: date) -> str:
        if cur is not None and _mi(p) == _mi(cur):
            return "current"
        if has_base and 1 <= _mi(cur) - _mi(p) <= baseline_months:
            return "baseline"
        return "other"

    return pd.DataFrame({"period": [p for p, _ in rows], "ratio": [r for _, r in rows], "role": [role(p) for p, _ in rows]})
