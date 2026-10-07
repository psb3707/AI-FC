"""OpenAI Provider (Optional). LLM 은 계산된 지표를 '설명'만 한다. 출력은 guardrails 로 검증한다."""
from __future__ import annotations

import json
import logging

import httpx

from src.insights.base import REQUIRED_DISCLAIMER, Brief, InsightProvider
from src.insights.guardrails import MAX_DEEP_DIVE, MAX_VALIDATION, violations
from src.insights.template_insight import TemplateInsightProvider

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""당신은 보험 FC의 상담 준비를 돕는 시장 브리핑 작성자입니다.
입력 JSON은 이미 Python으로 계산된 '검색 관심지수의 자기 과거 대비 변화' 지표입니다. 새로운 수치를 계산하거나 만들지 마세요. 입력에 있는 % 값만 인용하세요.
이 브리핑은 '시장 Signal -> 니즈 가설 -> FC 질문 -> 고객 검증' 중 앞의 두 단계만 돕습니다. 고객의 니즈를 판단하지 않습니다.

[절대 규칙]
- 보험상품·보험사를 추천하거나 가입/판매를 권유하지 않습니다. ("가입해야", "추천", "판매해야", "가장 좋은 보험" 등 금지)
- '검색량', '판매량', '수요' 가 늘었다고 쓰지 않습니다. 반드시 '검색 관심지수' / '검색 관심도'라고 씁니다.
- 서로 다른 Topic 의 크기를 비교해 '더 관심이 높다'고 쓰지 않습니다. 각 Topic 의 자기 과거 대비 변화만 설명합니다.
- 입력에 없는 원인(계기, 뉴스, 질병 위험 등)을 추측하지 않습니다. "~때문에", "~로 인해" 금지. 고객 니즈나 보험 필요를 단정하지 않습니다.
- reference_only 에 있는 Topic 은 해석에 쓰지 않고, 검색어 의미가 섞일 수 있어 제외했다고만 짧게 언급합니다.
- broad_move 가 있으면 여러 Topic 이 같은 방향으로 함께 움직인 것이므로 특정 영역의 변화로 단정하지 말고 신중히 해석하라고 씁니다.
- 입력의 headline/focus 와 직접 연결되는 내용만 씁니다. 일반적인 보험 상담 조언을 늘어놓지 않습니다.

[출력 구조] JSON 한 개만:
{{"what_changed": "데이터로 확인된 사실 1~2문장 (방향과 입력의 % 값만)",
 "interpretation": "과도한 추론 없이 상담 준비 관점 해석 2문장. 다음 문장을 반드시 그대로 포함: {REQUIRED_DISCLAIMER}",
 "validation_questions": ["Market Signal 이 실제 고객에게도 있는지 확인하는 열린 질문 (1~{MAX_VALIDATION}개)"],
 "deep_dive_questions": ["고객이 관심을 보일 때 더 탐색하는 열린 질문 (1~{MAX_DEEP_DIVE}개)"]}}
focus 가 있으면 focus 의 질문을 그대로 쓰거나 어미만 다듬습니다. focus 가 null 이면 특정 Topic 을 가정하지 않는 일반 질문을 씁니다."""


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
            brief = Brief(
                what_changed=str(data["what_changed"]), interpretation=str(data["interpretation"]),
                validation_questions=[str(q) for q in data["validation_questions"]],
                deep_dive_questions=[str(q) for q in data["deep_dive_questions"]], provider=self.name,
            )
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:
            log.warning("LLM brief failed: %s", e)
            return self._fallback_brief("AI 요약 생성에 실패하여 규칙 기반 요약으로 대체했습니다.", payload)
        bad = violations(brief, payload)
        if bad:
            log.warning("LLM brief rejected by guardrails: %s", bad)
            return self._fallback_brief("AI 요약이 안전 기준에 맞지 않아 규칙 기반 요약으로 대체했습니다.", payload)
        return brief

    def _fallback_brief(self, note: str, payload: dict) -> Brief:
        b = self._fallback.generate(payload)
        b.note = note
        return b
