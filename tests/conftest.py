import json
from pathlib import Path

import pytest

from src.config import AppConfig, load_topics

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def topics():
    return load_topics()


@pytest.fixture
def cfg():
    return AppConfig()


@pytest.fixture
def naver_response():
    return json.loads((FIX / "naver_datalab_response.json").read_text(encoding="utf-8"))
