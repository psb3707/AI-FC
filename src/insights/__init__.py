import os

from src.config import AppConfig
from src.insights.base import Brief, InsightProvider, build_payload
from src.insights.llm_insight import OpenAIInsightProvider
from src.insights.template_insight import TemplateInsightProvider


def get_provider(cfg: AppConfig) -> InsightProvider:
    """OPENAI_API_KEY 가 있고 ai.enabled 일 때만 LLM. 아니면 규칙 기반 (핵심 기능은 LLM 에 의존하지 않는다)."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if cfg.ai.enabled and key:
        return OpenAIInsightProvider(key, cfg.ai.model, cfg.ai.timeout_seconds)
    return TemplateInsightProvider()


__all__ = ["Brief", "InsightProvider", "build_payload", "get_provider"]
