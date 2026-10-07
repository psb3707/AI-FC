import pytest

from src.config import ConfigError, load_app_config, load_topics


def write(tmp_path, text):
    p = tmp_path / "topics.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_default_topics_load(topics):
    assert len(topics.topics) == 5
    assert topics.topics_version
    assert topics.keyword_groups[0]["groupName"] == "암보험"
    assert "암진단비" in topics.keyword_groups[0]["keywords"]


def test_app_config_loads():
    c = load_app_config()
    assert c.trend.up_threshold_pct == 5.0 and c.trend.baseline_months == 3


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_topics(tmp_path / "nope.yaml")


def test_empty_keywords(tmp_path):
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, "topics_version: v1\ntopics:\n  a: {display_name: A, keywords: []}\n"))


def test_missing_version(tmp_path):
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, "topics:\n  a: {display_name: A, keywords: [x]}\n"))


def test_too_many_topics(tmp_path):
    body = "".join(f"  t{i}: {{display_name: T{i}, keywords: [k{i}]}}\n" for i in range(6))
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, "topics_version: v1\ntopics:\n" + body))


def test_duplicate_display_name(tmp_path):
    text = (
        "topics_version: v1\ntopics:\n"
        "  a: {display_name: A, keywords: [x]}\n  b: {display_name: A, keywords: [y]}\n"
    )
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, text))


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, "topics: [unclosed"))


def test_no_topics(tmp_path):
    with pytest.raises(ConfigError):
        load_topics(write(tmp_path, "topics_version: v1\ntopics: {}\n"))
