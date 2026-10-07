from src.chart_data import topic_chart_frame
from src.models import Segment
from src.processing.normalizer import normalize
from src.processing.trend_calculator import compute_metrics


def test_chart_frame_marks_baseline_and_current(naver_response, topics, cfg):
    recs = normalize(naver_response, topics, "4", "male")
    m = compute_metrics(recs, topics, cfg.trend)[0]
    df = topic_chart_frame(recs, "cancer", m, cfg.trend.baseline_months)
    assert (df["role"] == "current").sum() == 1 and (df["role"] == "baseline").sum() == 3
    assert df.loc[df["role"] == "current", "period"].iloc[0] == m.current_period
    assert df.loc[df["role"] == "baseline", "ratio"].mean() == __import__("pytest").approx(m.three_month_avg, abs=0.01)


def test_chart_frame_no_baseline_when_unavailable(topics, cfg):
    from datetime import date
    from src.models import NormalizedRecord
    recs = [NormalizedRecord(period=date(2026, 9, 1), age_group="25~29", gender="male", topic="cancer", ratio=10)]
    m = compute_metrics(recs, topics, cfg.trend)[0]
    df = topic_chart_frame(recs, "cancer", m, 3)
    assert list(df["role"]) == ["current"]
