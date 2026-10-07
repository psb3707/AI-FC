"""규칙 기반 Brief. LLM 없이도 동작하며 LLM 실패 시 fallback 으로 쓴다. 수치는 payload 값만 인용."""
from __future__ import annotations

from src.insights.base import REQUIRED_DISCLAIMER, Brief, InsightProvider


def _fmt(v) -> str:
    return "계산 불가" if v is None else f"{v:+.1f}%"


class TemplateInsightProvider(InsightProvider):
    name = "template"

    def generate(self, payload: dict) -> Brief:
        seg = payload["segment"]["label"]
        topics = payload["topics"]
        ups = [t for t in topics if t["direction"] == "UP"]
        downs = [t for t in topics if t["direction"] == "DOWN"]
        known = [t for t in topics if t["direction"] != "UNKNOWN"]

        lines: list[str] = []
        if not known:
            lines.append(f"{seg} 구간은 변화 방향을 판단할 만큼 데이터가 충분하지 않습니다.")
        else:
            if ups:
                lines.append(
                    f"최근 {seg}에서 "
                    + ", ".join(f"{t['name']}(3개월 평균 대비 {_fmt(t['three_month_momentum_pct'])})" for t in ups)
                    + " 관련 검색 관심지수가 직전 3개월 평균보다 높게 나타났습니다."
                )
            if downs:
                lines.append(
                    ", ".join(f"{t['name']}(3개월 평균 대비 {_fmt(t['three_month_momentum_pct'])})" for t in downs)
                    + " 관련 검색 관심지수는 직전 3개월 평균보다 낮아졌습니다."
                )
            if not ups and not downs:
                lines.append(f"최근 {seg}에서 조회한 주제들의 검색 관심지수는 직전 3개월 평균과 비슷한 수준입니다.")
        lines.append(REQUIRED_DISCLAIMER + " 시장 분위기를 참고하는 하나의 가설로만 활용해 주세요.")

        focus = (ups + downs)[:1]
        qs: list[str] = []
        if focus:
            qs.append(f"최근 '{focus[0]['name']}' 같은 보장 영역에 관심을 가지게 된 계기나 걱정이 있으신가요?")
        qs.append("지금 가장 걱정되는 위험은 치료비, 소득 중단, 가족 부담 중 어느 쪽에 가까우신가요?")
        qs.append("현재 보유하신 보험과 월 보험료는 어느 정도까지 부담 가능하신지 말씀해 주실 수 있을까요?")
        return Brief(summary=" ".join(lines), questions=qs[:3], provider=self.name)
