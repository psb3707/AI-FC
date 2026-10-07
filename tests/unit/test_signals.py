from datetime import date

from src.insights.signals import build_consult_prep
from src.models import Direction, NormalizedRecord, Segment, SegmentReport, TopicMetric
from src.processing.trend_calculator import compute_metrics


def report(metrics):
    return SegmentReport(segment=Segment(age_code="7", gender="male"), data_source="real", metrics=metrics)


def tm(name, direction, mom):
    return TopicMetric(topic=name, display_name=name, direction=direction, momentum_pct=mom)


def test_prep_ranks_by_abs_momentum_and_focus_is_up(topics):
    r = report([
        tm("암보험", Direction.UP, 7.1), tm("실손보험", Direction.DOWN, -9.0),
        tm("종신보험", Direction.STABLE, 0.5), tm("간병보험", Direction.STABLE, -1.9),
    ])
    prep = build_consult_prep(r, topics)
    assert [s.topic for s in prep.headline] == ["실손보험", "암보험"]
    assert prep.focus.topic == "암보험"  # 하락 Topic 이 더 커도 질문은 상승 Topic 기준
    assert prep.stable_topics == ["종신보험", "간병보험"]
    assert prep.validation_question == topics.by_display_name("암보험").validation_question
    assert prep.check_point and prep.deep_dive_question


def test_cautioned_topic_excluded_from_headline_and_focus(topics):
    r = report([tm("건강보험", Direction.UP, 30.0), tm("암보험", Direction.STABLE, 1.0)])
    prep = build_consult_prep(r, topics)
    assert prep.headline == [] and prep.focus is None and prep.check_point is None
    assert [s.topic for s in prep.reference] == ["건강보험"] and prep.reference[0].caution


def test_unknown_goes_to_unknown(topics):
    prep = build_consult_prep(report([tm("암보험", Direction.UNKNOWN, None)]), topics)
    assert prep.unknown_topics == ["암보험"] and not prep.headline


def test_no_up_signal_has_no_focus(topics):
    prep = build_consult_prep(report([tm("암보험", Direction.DOWN, -12.0)]), topics)
    assert prep.headline[0].topic == "암보험" and prep.focus is None


def test_all_topics_have_question_bank_without_forbidden_words(topics):
    from src.insights.guardrails import FORBIDDEN_PHRASES
    for t in topics.topics:
        assert t.check_point and t.validation_question and t.deep_dive_question
        text = " ".join([t.check_point, t.validation_question, t.deep_dive_question])
        assert not any(p in text for p in FORBIDDEN_PHRASES)
        assert t.validation_question.endswith("?") and t.deep_dive_question.endswith("?")


def _recs(values, start=(2026, 1)):
    out, y, m = [], start[0], start[1]
    for v in values:
        out.append(NormalizedRecord(period=date(y, m, 1), age_group="x", gender="male", topic="cancer", ratio=v))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def test_rises_counts_positive_mom_in_last_six(topics, cfg):
    # 1월~9월: 10 11 12 11 13 14 15 14 16 -> 마지막 6개 MoM(4~9월): -,+,+,+,-,+ => 4회
    m = compute_metrics(_recs([10, 11, 12, 11, 13, 14, 15, 14, 16]), topics, cfg.trend)[0]
    assert (m.rises, m.rise_window) == (4, 6)


def test_rises_skips_gaps(topics, cfg):
    recs = [r for r in _recs([10, 11, 12, 13, 14, 15, 16, 17]) if r.period.month != 6]  # 6월 결측
    m = compute_metrics(recs, topics, cfg.trend)[0]
    assert m.rise_window == 4  # 6월을 낀 두 구간(6월, 7월)은 관측 불가


def test_broad_move_flag(topics):
    down3 = report([tm("암보험", Direction.DOWN, -7.0), tm("실손보험", Direction.DOWN, -8.0), tm("간병보험", Direction.DOWN, -9.0)])
    assert build_consult_prep(down3, topics).broad_move == Direction.DOWN
    two = report([tm("암보험", Direction.DOWN, -7.0), tm("실손보험", Direction.DOWN, -8.0), tm("간병보험", Direction.UP, 9.0)])
    assert build_consult_prep(two, topics).broad_move is None
