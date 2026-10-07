"""Mock Mode 데이터 생성기. 항상 DEMO DATA 로 표시되어야 하며 실제 데이터처럼 쓰면 안 된다.

Naver 와 같은 형태의 응답을 만들되, 5개 Topic 중 최댓값이 100 이 되도록 정규화한다.
Segment/기간으로 seed 를 고정해 같은 조건이면 같은 결과가 나온다 (테스트 가능).
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date
from typing import Any

from src.models import RequestMeta


def _months(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build_mock_response(meta: RequestMeta) -> dict[str, Any]:
    months = _months(meta.start_date, meta.end_date)
    seed_src = f"{meta.age_codes}|{meta.gender}|{meta.start_date}|{meta.end_date}"
    rng = random.Random(int(hashlib.md5(seed_src.encode()).hexdigest()[:8], 16))
    raw: dict[str, list[float]] = {}
    for name in meta.topic_groups:
        base = rng.uniform(30, 70)
        trend = rng.uniform(-1.2, 2.2)
        amp, phase = rng.uniform(2, 8), rng.uniform(0, 6.28)
        raw[name] = [
            max(1.0, base + trend * i + amp * math.sin(i / 2 + phase) + rng.uniform(-3, 3)) for i in range(len(months))
        ]
    peak = max((v for series in raw.values() for v in series), default=1.0)
    results = [
        {
            "title": name,
            "keywords": meta.topic_groups[name],
            "data": [{"period": d.isoformat(), "ratio": round(v / peak * 100, 5)} for d, v in zip(months, series)],
        }
        for name, series in raw.items()
    ]
    return {
        "startDate": meta.start_date.isoformat(),
        "endDate": meta.end_date.isoformat(),
        "timeUnit": meta.time_unit,
        "results": results,
    }
