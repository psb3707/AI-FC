"""AI Brief 출력 검증. 금칙어 / 필수 문구 / 질문 수 / 판매량·검색량 단정 표현."""
from __future__ import annotations

import re

from src.insights.base import Brief

FORBIDDEN_PHRASES = [
    "반드시 가입", "이 상품을 추천", "판매해야", "가입해야 한다", "가입해야 합니다", "가장 좋은 보험",
    "추천드립니다", "가입을 권장", "가입을 권유", "가입하세요",
]
# 검색 관심지수를 검색량/판매량/수요로 단정하는 표현
FORBIDDEN_PATTERNS = [
    r"검색량\s*(이|은)?\s*[+\-]?\d",   # "검색량 18% 증가"
    r"검색량[^.。]{0,10}(증가|감소|늘|줄)",
    r"판매(량|가)?[^.。]{0,8}(증가|늘|상승)",
    r"수요[가이]?\s*[^.。]{0,6}(증가|늘)",
]
MAX_QUESTIONS = 3
DISCLAIMER_KEYS = ("판매량", "필요성")  # 필수 의미: 판매량·개인 필요성 아님


def violations(brief: Brief) -> list[str]:
    text = brief.summary + "\n" + "\n".join(brief.questions)
    found = [f"금칙어: {p}" for p in FORBIDDEN_PHRASES if p in text]
    found += [f"단정 표현: {p}" for p in FORBIDDEN_PATTERNS if re.search(p, text)]
    if len(brief.questions) > MAX_QUESTIONS:
        found.append(f"질문 {len(brief.questions)}개 (최대 {MAX_QUESTIONS})")
    if not brief.questions:
        found.append("상담 질문 없음")
    if not all(k in brief.summary for k in DISCLAIMER_KEYS):
        found.append("검색 관심도 ≠ 판매량/개인 필요성 문구 누락")
    return found
