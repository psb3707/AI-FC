from datetime import date

import pytest

from src.config import TrendConfig
from src.models import Direction
from src.processing.trend_calculator import classify, compute_topic_metric

CFG = TrendConfig()


def series(values, start=(2026, 1)):
    y, m = start
    out = []
    for v in values:
        out.append((date(y, m, 1), v))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def test_mom_and_momentum_values():
    # 직전 3개월 60,65,70 -> 평균 65, 이번 달 78 (명세 §20 예시)
    m = compute_topic_metric("t", "T", series([60, 65, 70, 78]), CFG)
    assert m.current_index == 78
    assert m.mom_pct == pytest.approx((78 - 70) / 70 * 100, abs=0.01)
    assert m.three_month_avg == 65
    assert m.momentum_pct == pytest.approx((78 - 65) / 65 * 100, abs=0.01)
    assert m.direction == Direction.UP


def test_spec_mom_example():
    m = compute_topic_metric("t", "T", series([50, 55, 60, 72]), CFG)  # 60 -> 72
    assert m.mom_pct == pytest.approx(20.0)


@pytest.mark.parametrize(
    "mom,expected",
    [
        (5.0, Direction.UP),
        (4.99, Direction.STABLE),
        (0, Direction.STABLE),
        (-4.99, Direction.STABLE),
        (-5.0, Direction.DOWN),
        (-30, Direction.DOWN),
        (None, Direction.UNKNOWN),
        (float("nan"), Direction.UNKNOWN),
    ],
)
def test_classify_thresholds(mom, expected):
    assert classify(mom, CFG) == expected


def test_threshold_is_configurable():
    assert classify(7, TrendConfig(up_threshold_pct=10)) == Direction.STABLE


def test_previous_zero_is_safe():
    m = compute_topic_metric("t", "T", series([10, 10, 0, 50]), CFG)
    assert m.mom_pct is None
    assert m.momentum_pct is not None  # 평균 6.67 > 0
    assert "MoM" in m.note


def test_baseline_avg_zero_is_safe():
    m = compute_topic_metric("t", "T", series([0, 0, 0, 5]), CFG)
    assert m.momentum_pct is None and m.direction == Direction.UNKNOWN


def test_empty_series():
    m = compute_topic_metric("t", "T", [], CFG)
    assert m.current_index is None and m.direction == Direction.UNKNOWN and m.note == "데이터 없음"


def test_single_month():
    m = compute_topic_metric("t", "T", series([42]), CFG)
    assert m.current_index == 42 and m.mom_pct is None and m.momentum_pct is None
    assert m.direction == Direction.UNKNOWN


def test_fewer_than_three_baseline_months():
    m = compute_topic_metric("t", "T", series([40, 50, 60]), CFG)  # 직전 2개월뿐
    assert m.mom_pct == pytest.approx(20.0)
    assert m.momentum_pct is None and m.direction == Direction.UNKNOWN


def test_gap_in_months_is_not_treated_as_previous():
    pts = [(date(2026, 1, 1), 50.0), (date(2026, 2, 1), 55.0), (date(2026, 4, 1), 60.0)]  # 3월 누락
    assert compute_topic_metric("t", "T", pts, CFG).mom_pct is None


def test_none_and_nan_values_ignored():
    pts = series([50, 55, 60, 65]) + [(date(2026, 5, 1), None), (date(2026, 6, 1), float("nan"))]
    assert compute_topic_metric("t", "T", pts, CFG).current_index == 65


def test_unsorted_input():
    pts = list(reversed(series([60, 65, 70, 78])))
    assert compute_topic_metric("t", "T", pts, CFG).current_index == 78
