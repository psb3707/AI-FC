from datetime import date

import pytest

from src.models import Direction
from src.processing.normalizer import MalformedResponseError, normalize
from src.processing.trend_calculator import compute_metrics


def test_fixture_parsing(naver_response, topics):
    recs = normalize(naver_response, topics, "4", "male")
    assert len(recs) == 60
    cancer = [r for r in recs if r.topic == "cancer"]
    assert cancer[0].period == date(2025, 10, 1) and cancer[0].ratio == 47.0
    assert cancer[-1].period == date(2026, 9, 1) and cancer[-1].ratio == 78.2
    assert {r.age_group for r in recs} == {"25~29"} and {r.gender for r in recs} == {"male"}


def test_fixture_metrics_end_to_end(naver_response, topics, cfg):
    ms = {m.topic: m for m in compute_metrics(normalize(naver_response, topics, "4", "male"), topics, cfg.trend)}
    assert ms["cancer"].direction == Direction.UP
    assert ms["whole_life"].direction == Direction.DOWN
    assert ms["indemnity"].direction == Direction.STABLE
    assert ms["cancer"].mom_pct == pytest.approx((78.2 - 66.0) / 66.0 * 100, abs=0.01)
    assert ms["cancer"].three_month_avg == pytest.approx((63.1 + 60.5 + 66.0) / 3, abs=0.01)


def test_empty_results(topics):
    assert normalize({"results": []}, topics, "4", "all") == []


@pytest.mark.parametrize(
    "bad", [None, [], "x", {}, {"results": "x"}, {"results": [1]}, {"results": [{"title": "암보험"}]}]
)
def test_malformed(bad, topics):
    with pytest.raises(MalformedResponseError):
        normalize(bad, topics, "4", "all")


def test_bad_items_skipped_and_unknown_title_ignored(topics):
    raw = {
        "results": [
            {
                "title": "암보험",
                "data": [
                    {"period": "2026-01-01", "ratio": 10},
                    {"period": "bad", "ratio": 1},
                    {"ratio": 3},
                    {"period": "2026-02-01", "ratio": "x"},
                ],
            },
            {"title": "모르는토픽", "data": [{"period": "2026-01-01", "ratio": 5}]},
        ]
    }
    recs = normalize(raw, topics, "4", "male")
    assert len(recs) == 1 and recs[0].topic == "cancer"
