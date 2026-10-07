"""AI Brief 출력 검증. 금칙어 / 필수 문구 / 질문 수 / 판매량·검색량 단정 / 근거 없는 수치·원인·니즈 단정."""
from __future__ import annotations

import re
from typing import Optional

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
# 데이터에서 확인할 수 없는 원인 / 고객 니즈·질병 위험 단정
UNSUPPORTED_PATTERNS = [
    r"(때문에|때문입니다|로 인해|으로 인해|원인은|영향으로)",
    r"(필요합니다|필요하다|필요하며|필요해 보입니다|필요로 합니다)",
    r"(니즈|수요)[가는]?\s*(있|높|커|크|증가|확대|존재)",
    r"(위험|발병|발생)[이가]?\s*(높|커|증가)",
]
MAX_VALIDATION = 2
MAX_DEEP_DIVE = 2
DISCLAIMER_KEYS = ("판매량", "필요성")  # 필수 의미: 판매량·개인 필요성 아님
_PCT = re.compile(r"[+\-−]?\s*(\d+(?:\.\d+)?)\s*%")


def allowed_numbers(payload: dict) -> set[float]:
    """payload 에 있는 % 값(절댓값, 소수 1자리)만 본문에 인용할 수 있다."""
    out: set[float] = set()
    for t in payload.get("topics", []):
        for k in ("mom_pct", "three_month_momentum_pct"):
            v = t.get(k)
            if v is not None:
                out.add(round(abs(v), 1))
    return out


def violations(brief: Brief, payload: Optional[dict] = None) -> list[str]:
    text = brief.text + "\n" + "\n".join(brief.questions)
    found = [f"금칙어: {p}" for p in FORBIDDEN_PHRASES if p in text]
    found += [f"단정 표현: {p}" for p in FORBIDDEN_PATTERNS if re.search(p, text)]
    # 원인/니즈 단정은 '주장'(사실·해석 문장)에만 적용한다. 질문은 고객에게 묻는 문장이므로 제외.
    found += [f"근거 없는 원인/니즈 단정: {p}" for p in UNSUPPORTED_PATTERNS if re.search(p, brief.text)]
    if len(brief.validation_questions) > MAX_VALIDATION:
        found.append(f"Signal Validation 질문 {len(brief.validation_questions)}개 (최대 {MAX_VALIDATION})")
    if len(brief.deep_dive_questions) > MAX_DEEP_DIVE:
        found.append(f"Need Deep-Dive 질문 {len(brief.deep_dive_questions)}개 (최대 {MAX_DEEP_DIVE})")
    if not brief.validation_questions or not brief.deep_dive_questions:
        found.append("상담 질문 없음 (Signal Validation / Need Deep-Dive 각 1개 이상)")
    if not brief.what_changed.strip() or not brief.interpretation.strip():
        found.append("What Changed / How to Interpret 누락")
    if not all(k in brief.interpretation for k in DISCLAIMER_KEYS):
        found.append("검색 관심도 ≠ 판매량/개인 필요성 문구 누락 (How to Interpret)")
    if payload is not None:
        ok = allowed_numbers(payload)
        for m in _PCT.finditer(brief.text):
            if round(float(m.group(1)), 1) not in ok:
                found.append(f"payload 에 없는 수치: {m.group(0).strip()}")
    return found
