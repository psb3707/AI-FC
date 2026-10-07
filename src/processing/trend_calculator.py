"""Trend 지표 계산 (project-defined metrics). 모든 수치 계산은 여기서만 한다.

- MoM%      = (Current - Prev) / Prev * 100        (Prev <= 0 이면 None)
- 3M Avg    = Current 직전 baseline_months(=3)개월 평균 (Current 제외)
- Momentum% = (Current - 3M Avg) / 3M Avg * 100   (평균 <= 0 이면 None)
- Direction = threshold 기준 UP / STABLE / DOWN, 계산 불가면 UNKNOWN
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

from src.config import TopicsConfig, TrendConfig
from src.models import Direction, NormalizedRecord, TopicMetric


def _month_index(d: date) -> int:
    return d.year * 12 + d.month


def pct_change(current: float, base: Optional[float]) -> Optional[float]:
    if base is None or current is None or base <= 0:
        return None
    return (current - base) / base * 100.0


def classify(momentum_pct: Optional[float], cfg: TrendConfig) -> Direction:
    if momentum_pct is None or math.isnan(momentum_pct):
        return Direction.UNKNOWN
    if momentum_pct >= cfg.up_threshold_pct:
        return Direction.UP
    if momentum_pct <= cfg.down_threshold_pct:
        return Direction.DOWN
    return Direction.STABLE


def compute_topic_metric(
    topic: str, display_name: str, series: Iterable[tuple[date, float]], cfg: TrendConfig
) -> TopicMetric:
    pts = sorted(
        ((p, float(r)) for p, r in series if p is not None and r is not None and not math.isnan(float(r))),
        key=lambda x: x[0],
    )
    # 같은 월 중복 시 마지막 값 사용
    by_month = {_month_index(p): (p, r) for p, r in pts}
    m = TopicMetric(topic=topic, display_name=display_name, n_points=len(by_month))
    if not by_month:
        m.note = "데이터 없음"
        return m

    cur_idx = max(by_month)
    cur_period, current = by_month[cur_idx]
    m.current_period, m.current_index = cur_period, round(current, 2)

    notes: list[str] = []
    prev = by_month.get(cur_idx - 1)
    if prev is None:
        notes.append("전월 데이터 없음")
    else:
        mom = pct_change(current, prev[1])
        if mom is None:
            notes.append("전월 값이 0 이하여서 MoM 계산 불가")
        else:
            m.mom_pct = round(mom, 2)

    baseline = [by_month.get(cur_idx - k) for k in range(1, cfg.baseline_months + 1)]
    if any(b is None for b in baseline):
        notes.append(f"직전 {cfg.baseline_months}개월 데이터 부족")
    else:
        avg = sum(b[1] for b in baseline) / cfg.baseline_months  # type: ignore[index]
        m.three_month_avg = round(avg, 2)
        mo = pct_change(current, avg)
        if mo is None:
            notes.append("3개월 평균이 0 이하여서 Momentum 계산 불가")
        else:
            m.momentum_pct = round(mo, 2)

    m.direction = classify(m.momentum_pct, cfg)
    m.note = "; ".join(notes) or None
    return m


def compute_metrics(
    records: list[NormalizedRecord], topics: TopicsConfig, cfg: TrendConfig
) -> list[TopicMetric]:
    """Topic 설정 순서대로 지표를 반환. 데이터가 없는 Topic 도 UNKNOWN 으로 포함."""
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in records:
        series[r.topic].append((r.period, r.ratio))
    return [
        compute_topic_metric(t.id, t.display_name, series.get(t.id, []), cfg) for t in topics.topics
    ]
