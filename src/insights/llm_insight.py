"""OpenAI Provider (Optional). LLM 은 계산된 지표를 '설명'만 한다. 출력은 guardrails 로 검증한다."""
from __future__ import annotations

import json
import logging

import httpx

from src.insights.base import REQUIRED_DISCLAIMER, Brief, InsightProvider
from src.insights.guardrails import MAX_QUESTIONS, violations
from src.insights.template_insight import TemplateInsightProvider

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""당신은 보험 FC의 상담 준비를 돕는 시장 브리핑 작성자입니다.
입력 JSON은 이미 Python으로 계산된 '검색 관심지수' 지표입니다. 새로운 수치를 계산하거나 만들지 마세요. 입력에 있는 값만 인용하세요.

[절대 규칙]
- 보험상품·보험사를 추천하거나 가입/판매를 권유하지 않습니다. ("가입해야", "추천", "판매해야", "가장 좋은 보험" 등 금지)
- '검색량', '판매량', '수요' 가 늘었다고 쓰지 않습니다. 반드시 '검색 관심지수' / '검색 관심도'라고 씁니다.
- 서로 다른 Topic 의 current_index 크기를 비교해 '더 관심이 높다'고 쓰지 않습니다. 각 Topic 의 자기 과거 대비 변화만 설명합니다.
- summary 에 다음 의미의 문장을 반드시 그대로 포함합니다: "{REQUIRED_DISCLAIMER}"
- 상담 질문은 고객의 니즈를 파악하는 열린 질문(Needs Discovery)이며 최대 {MAX_QUESTIONS}개입니다. 상품 판매 문구가 아닙니다.

[출력] JSON 한 개만: {{"summary": "3~5문장", "questions": ["...", "..."]}}"""


class OpenAIInsightProvider(InsightProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 30, client: httpx.Client | None = None):
        self._key, self._model = api_key, model
        self._client = client or httpx.Client(timeout=timeout)
        self._fallback = TemplateInsightProvider()

    def generate(self, payload: dict) -> Brief:
        try:
            resp = self._client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self._model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
            brief = Brief(summary=str(data["summary"]), questions=[str(q) for q in data["questions"]], provider=self.name)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:
            log.warning("LLM brief failed: %s", e)
            return self._fallback_brief("AI 요약 생성에 실패하여 규칙 기반 요약으로 대체했습니다.", payload)
        bad = violations(brief)
        if bad:
            log.warning("LLM brief rejected by guardrails: %s", bad)
            return self._fallback_brief("AI 요약이 안전 기준에 맞지 않아 규칙 기반 요약으로 대체했습니다.", payload)
        return brief

    def _fallback_brief(self, note: str, payload: dict) -> Brief:
        b = self._fallback.generate(payload)
        b.note = note
        return b
