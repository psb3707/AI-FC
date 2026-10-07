# ROADMAP

## v0.1 (이 PoC)
Segment 선택, 5 Topic Trend, Chart, AI Brief(옵션), Mock Mode, 문서/테스트.

## 검증 후 후보 (이번 범위 아님 — 기록만)
- 실제 API Smoke Test 3종 수행 결과로 Topic 간 비교 UI 확정 (Test 1~3, DATA_METHODOLOGY §7)
- 건강보험 Keyword 재설계(현업 검토) 후 `topics_version` 상향 및 §8 실험 재수행 (현재는 caution 처리)
- 연령 인접 구간 비교(동일 Request 불가 → 별도 정규화 전략 필요)
- 기기(PC/모바일) 분석, 상세 보기용 주간 단위 (기본은 월 단위 유지)
- 12개월 이상 이력으로 계절성 보정/동시 하락(broad move) 판별
- OpenAI 경로 실호출 검증 및 LLM 답변의 Topic·방향 일치 자동 검사 강화
- 현업 FC 3~5명 대상 30초 이해도 테스트(아래 PRODUCT_REVIEW 의 자체 평가는 대체 불가)
- 현업 FC 피드백 수집 (30초 이해도, 상담 질문 유용성)
- 외부 데이터 연계(HIRA, KDCA, 보험다모아 등), SFA 연동, Next Best Action — **PoC 가설 검증 이후 별도 판단**
