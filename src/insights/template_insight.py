"""규칙 기반 Brief. LLM 없이도 동작하며 LLM 실패 시 fallback 으로 쓴다. 수치는 payload 값만 인용."""
from __future__ import annotations

from src.insights.base import (
    GENERIC_DEEP_DIVE_QUESTION, GENERIC_VALIDATION_QUESTION, REQUIRED_DISCLAIMER, Brief, InsightProvider,
)


def _fmt(v) -> str:
    return "계산 불가" if v is None else f"{v:+.1f}%"


def _join(items: list[str]) -> str:
    return ", ".join(items)


class TemplateInsightProvider(InsightProvider):
    name = "template"

    def generate(self, payload: dict) -> Brief:
        seg = payload["segment"]["label"]
        reference = {r["name"] for r in payload.get("reference_only", [])}
        # 데이터 품질 경고 Topic 은 사실/해석에서 제외 (참고로만 언급)
        topics = [t for t in payload["topics"] if t["name"] not in reference]
        ups = [t for t in topics if t["direction"] == "UP"]
        downs = [t for t in topics if t["direction"] == "DOWN"]
        known = [t for t in topics if t["direction"] != "UNKNOWN"]

        def with_pct(ts):
            return _join([f"{t['name']}(3개월 평균 대비 {_fmt(t['three_month_momentum_pct'])})" for t in ts])

        facts: list[str] = []
        if not known:
            facts.append(f"{seg} 구간은 변화 방향을 판단할 만큼 데이터가 충분하지 않습니다.")
        else:
            if ups:
                facts.append(f"최근 {seg}에서 {with_pct(ups)} 관련 검색 관심지수가 직전 3개월 평균보다 높게 나타났습니다.")
            if downs:
                facts.append(f"{with_pct(downs)} 관련 검색 관심지수는 직전 3개월 평균보다 낮아졌습니다.")
            if not ups and not downs:
                facts.append(f"최근 {seg}에서 조회한 주제들의 검색 관심지수는 직전 3개월 평균과 비슷한 수준입니다.")
        if reference:
            facts.append(f"{_join(sorted(reference))} 항목은 검색어 의미가 섞일 수 있어 해석에서 제외했습니다.")

        focus = payload.get("focus")
        if focus:
            interp = (
                f"전체 보험 관심이 늘었다고 판단하기보다는 '{focus['name']}' 보장 영역에 대한 관심 변화 가능성을 "
                "탐색해 볼 수 있는 Signal입니다."
            )
        elif downs:
            interp = "관심이 낮아진 영역이 있어도 고객의 필요가 줄었다는 뜻은 아니므로, 먼저 고객의 현재 상황을 확인하는 것이 좋습니다."
        else:
            interp = "뚜렷한 방향성이 없으므로 시장 Signal보다 고객의 개인 상황을 먼저 확인하는 상담 준비가 적합합니다."
        if payload.get("broad_move"):
            interp += " 여러 주제가 같은 방향으로 함께 움직였으므로, 특정 보장 영역의 변화로 읽기에는 신중하게 해석해 주세요."
        interp += " " + REQUIRED_DISCLAIMER + " 상담 시작을 위한 하나의 가설로만 활용해 주세요."

        validation = (focus or {}).get("validation_question") or GENERIC_VALIDATION_QUESTION
        deep = (focus or {}).get("deep_dive_question") or GENERIC_DEEP_DIVE_QUESTION
        return Brief(
            what_changed=" ".join(facts), interpretation=interp,
            validation_questions=[validation], deep_dive_questions=[deep], provider=self.name,
        )
