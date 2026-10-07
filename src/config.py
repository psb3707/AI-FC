"""config/*.yaml 로딩 및 검증. 잘못된 Topic 설정은 ConfigError."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

ROOT = Path(__file__).resolve().parent.parent
MAX_GROUPS = 5  # Naver: request 당 keywordGroups 최대 5
MAX_KEYWORDS = 20  # Naver: group 당 keywords 최대 20


class ConfigError(ValueError):
    pass


class Topic(BaseModel):
    id: str
    display_name: str
    keywords: list[str]
    caution: Optional[str] = None  # 검색어 의미 혼재 등 데이터 품질 경고 (있으면 UI 표시, 헤드라인 Signal 에서 제외)
    check_point: Optional[str] = None  # 관심 상승 시 FC 가 먼저 확인할 영역 (제안이 아닌 확인 사항)
    validation_question: Optional[str] = None  # Signal Validation 질문
    deep_dive_question: Optional[str] = None  # Need Deep-Dive 질문 (고객이 관심을 표현한 경우)

    @field_validator("keywords")
    @classmethod
    def _check_keywords(cls, v: list[str]) -> list[str]:
        v = [k.strip() for k in v if isinstance(k, str) and k.strip()]
        if not v:
            raise ValueError("keywords가 비어 있습니다")
        if len(v) > MAX_KEYWORDS:
            raise ValueError(f"keyword는 그룹당 최대 {MAX_KEYWORDS}개")
        return v


class TopicsConfig(BaseModel):
    topics_version: str
    topics: list[Topic]

    @property
    def keyword_groups(self) -> list[dict]:
        return [{"groupName": t.display_name, "keywords": t.keywords} for t in self.topics]

    def by_display_name(self, name: str) -> Optional[Topic]:
        return next((t for t in self.topics if t.display_name == name), None)


class TrendConfig(BaseModel):
    up_threshold_pct: float = 5.0
    down_threshold_pct: float = -5.0
    baseline_months: int = 3
    persistence_months: int = 6  # '최근 N개월 중 상승 횟수' 보조 지표 구간

    @field_validator("baseline_months")
    @classmethod
    def _pos(cls, v: int) -> int:
        if v < 1:
            raise ValueError("baseline_months >= 1")
        return v


class CollectorConfig(BaseModel):
    timeout_seconds: float = 10
    max_retries: int = 3
    backoff_seconds: float = 1.0
    min_interval_seconds: float = 0.2


class CacheConfig(BaseModel):
    ttl_hours: float = 24


class PeriodsConfig(BaseModel):
    options: list[int] = [6, 12, 24]
    default: int = 12


class DefaultsConfig(BaseModel):
    age_code: str = "4"
    gender: str = "male"


class AIConfig(BaseModel):
    enabled: bool = True
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 30


class AppConfig(BaseModel):
    trend: TrendConfig = Field(default_factory=TrendConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    periods: PeriodsConfig = Field(default_factory=PeriodsConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    ai: AIConfig = Field(default_factory=AIConfig)


def _load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML 파싱 오류 ({path.name}): {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: 최상위는 mapping 이어야 합니다")
    return data


def load_topics(path: Path | None = None) -> TopicsConfig:
    path = path or ROOT / "config" / "topics.yaml"
    data = _load_yaml(path)
    raw_topics = data.get("topics")
    if not isinstance(raw_topics, dict) or not raw_topics:
        raise ConfigError("topics.yaml: 'topics' 가 비어 있거나 mapping 이 아닙니다")
    if len(raw_topics) > MAX_GROUPS:
        raise ConfigError(f"Topic은 한 Request 당 최대 {MAX_GROUPS}개 (현재 {len(raw_topics)})")
    topics: list[Topic] = []
    try:
        for tid, body in raw_topics.items():
            if not isinstance(body, dict):
                raise ConfigError(f"topic '{tid}' 형식 오류")
            extra = {k: body[k] for k in ("caution", "check_point", "validation_question", "deep_dive_question") if body.get(k)}
            topics.append(Topic(id=str(tid), display_name=body.get("display_name", ""), keywords=body.get("keywords", []), **extra))
        version = data.get("topics_version")
        if not version:
            raise ConfigError("topics.yaml: topics_version 이 필요합니다")
        cfg = TopicsConfig(topics_version=str(version), topics=topics)
    except ValidationError as e:
        raise ConfigError(f"topics.yaml 검증 실패: {e}") from e
    names = [t.display_name for t in cfg.topics]
    if any(not n.strip() for n in names):
        raise ConfigError("display_name 이 비어 있는 topic 이 있습니다")
    if len(set(names)) != len(names):
        raise ConfigError("display_name 이 중복되었습니다")
    return cfg


def load_app_config(path: Path | None = None) -> AppConfig:
    path = path or ROOT / "config" / "app_config.yaml"
    try:
        return AppConfig(**_load_yaml(path))
    except ValidationError as e:
        raise ConfigError(f"app_config.yaml 검증 실패: {e}") from e


def app_mode() -> str:
    mode = os.getenv("APP_MODE", "mock").strip().lower()
    return mode if mode in ("mock", "real") else "mock"
