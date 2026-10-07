"""실제 Naver API 호출. 기본 실행에서는 제외된다: `pytest -m integration`
NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없으면 skip."""
import os
from datetime import date

import pytest
from dotenv import load_dotenv

from src.collectors.naver_datalab import NaverDataLabCollector
from src.config import ROOT
from src.processing.normalizer import normalize
from src.service import window
from src.storage.repository import Repository

load_dotenv(ROOT / ".env")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET")), reason="Naver API 키 없음"),
]


def test_live_age4_male_cancer_3m(tmp_path, topics):
    start, end = window(3)
    groups = [g for g in topics.keyword_groups if g["groupName"] == "암보험"]
    col = NaverDataLabCollector(os.environ["NAVER_CLIENT_ID"], os.environ["NAVER_CLIENT_SECRET"])
    raw = col.fetch_trends(start, end, "month", groups, age_code="4", gender="m", topics_version=topics.topics_version)

    recs = normalize(raw.response, topics, "4", "male")
    assert recs, "데이터가 파싱되어야 함"
    assert all(start <= r.period <= end for r in recs)  # 날짜 정상
    assert all(0 <= r.ratio <= 100 for r in recs)  # ratio 범위 정상
    assert max(r.ratio for r in recs) == pytest.approx(100, abs=0.01)  # 요청 내 최댓값 = 100

    repo = Repository(tmp_path / "c.sqlite3", tmp_path / "raw")
    assert repo.save_raw(raw.meta, raw.response).exists()  # Storage 정상
    repo.put_cache(raw.meta, raw.response)
    assert repo.get_cache(raw.meta, 24) is not None
