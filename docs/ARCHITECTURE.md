# ARCHITECTURE

실제 코드(`src/`) 기준 구조도. Mermaid 는 GitHub / VS Code(Markdown Preview Mermaid) 에서 렌더링된다.

## 1. 전체 시스템 구조

```mermaid
flowchart TB
    FC([FC 사용자])

    subgraph UI["Presentation — app.py (Streamlit)"]
        FILTER["필터: Age / Gender / Period"]
        BANNER["DEMO DATA 배너 · Disclaimer · 기준월"]
        CARDS["Trend 카드 5개"]
        CHART["Trend 차트 (Topic 선택)"]
        BRIEF["AI Monthly Brief + 상담 질문"]
    end

    subgraph CFG["Config — config/*.yaml, .env"]
        TOPICS["topics.yaml<br/>Topic·Keyword·topics_version"]
        APPCFG["app_config.yaml<br/>임계값·TTL·기간·AI"]
        ENV[".env<br/>APP_MODE · NAVER Key · OPENAI Key"]
    end

    SVC["ReportService — src/service.py<br/>조회 오케스트레이션 · 오류 → 사용자 메시지"]

    subgraph COLLECT["Collection"]
        COL["NaverDataLabCollector<br/>timeout · retry(최대 3) · 4xx 즉시 실패 · 호출 간격"]
        MOCK["Mock generator<br/>APP_MODE=mock · DEMO DATA"]
    end

    NAVER[("Naver DataLab API<br/>POST /v1/datalab/search<br/>일 1,000회")]

    subgraph STORE["Storage — src/storage/repository.py"]
        RAW[("Raw JSON 파일<br/>data/raw/naver/날짜/*.json<br/>metadata + 원본 응답")]
        CACHE[("SQLite 캐시<br/>data/processed/cache.sqlite3<br/>TTL 24h")]
    end

    subgraph PROC["Processing — src/processing/"]
        NORM["Normalizer<br/>Raw → NormalizedRecord"]
        TREND["Trend Calculator<br/>Current · MoM · 3M Momentum · Direction"]
    end

    subgraph INSIGHT["Insight — src/insights/"]
        PAYLOAD["build_payload<br/>계산된 지표만 전달 (Raw 미전달)"]
        PROV{{"InsightProvider"}}
        TMPL["TemplateInsightProvider<br/>규칙 기반 (LLM 불필요)"]
        LLM["OpenAIInsightProvider<br/>(Optional)"]
        GUARD["Guardrails<br/>금칙어 · 필수 문구 · 질문 ≤ 3"]
    end

    OPENAI(["OpenAI API"])

    FC --> FILTER
    FILTER --> SVC
    ENV -. 모드·Key .-> SVC
    TOPICS -. keywordGroups .-> SVC
    APPCFG -. 임계값·TTL .-> SVC

    SVC -- "mode = real" --> CACHE
    CACHE -- "HIT" --> NORM
    CACHE -- "MISS" --> COL
    COL <--> NAVER
    COL --> RAW
    COL --> CACHE
    COL --> NORM
    SVC -- "mode = mock" --> MOCK --> NORM

    NORM --> TREND
    TREND -->|SegmentReport| SVC

    SVC --> BANNER
    SVC --> CARDS
    SVC --> CHART
    SVC --> PAYLOAD --> PROV
    PROV --> TMPL
    PROV --> LLM <--> OPENAI
    LLM --> GUARD
    GUARD -- "통과" --> BRIEF
    GUARD -- "위반 → 대체" --> TMPL
    TMPL --> BRIEF
    CARDS --> FC
    CHART --> FC
    BRIEF --> FC
```

## 2. 요청 흐름 (실데이터 모드)

```mermaid
sequenceDiagram
    actor FC
    participant UI as Streamlit (app.py)
    participant S as ReportService
    participant DB as SQLite 캐시
    participant C as Collector
    participant N as Naver DataLab
    participant R as Raw 파일
    participant P as Normalizer + Trend
    participant I as InsightProvider

    FC->>UI: 연령·성별·기간 선택
    UI->>S: get_report(segment, months)
    S->>DB: 캐시 조회 (조건+topics_version+keyword)
    alt 캐시 HIT (TTL 이내)
        DB-->>S: Raw 응답 + metadata
    else 캐시 MISS
        S->>C: fetch_trends (1 Segment = 1 Age Code, 5 Topic 1 Request)
        C->>N: POST /v1/datalab/search
        N-->>C: ratio 시계열
        C-->>S: Raw 응답 + metadata
        S->>R: 원본 저장 (수정 없음)
        S->>DB: 캐시 저장
    end
    S->>P: normalize → compute_metrics
    P-->>S: SegmentReport (지표)
    S-->>UI: report (또는 error 메시지)
    UI->>I: build_payload(지표만)
    I-->>UI: Brief (요약 + 상담 질문 ≤ 3)
    UI-->>FC: 카드 · 차트 · Brief · Disclaimer
```

## 3. 설계 원칙 (다이어그램에 반영된 부분)

| 원칙 | 구조상 반영 |
|---|---|
| 계산은 Python, AI 는 설명만 | LLM 은 `build_payload` 의 계산된 지표만 입력으로 받음 (Trend Calculator 뒤에 위치) |
| LLM 없이도 핵심 기능 동작 | Provider 가 `TemplateInsightProvider` 로 분리, Key 없으면 자동 사용 |
| AI 출력 통제 | Guardrails 위반·LLM 실패 시 Template 로 대체 |
| Mock/실데이터 혼동 방지 | Mock 은 Raw·캐시에 저장하지 않고 `DEMO DATA` 배너 고정 |
| ratio 재정규화 문제 | 캐시 키에 기간·성별·연령·keyword 포함, 같은 윈도우를 한 번에 재조회 |
| 장애 격리 | Service 가 모든 예외를 `SegmentReport.error` 로 변환 → UI 는 Crash 없이 안내 |
