# ROADMAP

## v0.1 (이 PoC)
Segment 선택, 5 Topic Trend, Chart, AI Brief(옵션), Mock Mode, 문서/테스트.

## 검증 후 후보 (이번 범위 아님 — 기록만)
- 실제 API Smoke Test 3종 수행 결과로 Topic 간 비교 UI 확정 (Test 1~3, DATA_METHODOLOGY §7)
- Topic/Keyword 편향 검토 (예: "건강보험"의 국민건강보험 혼입) 및 `topics_version` 이력 관리
- 연령 인접 구간 비교(동일 Request 불가 → 별도 정규화 전략 필요)
- 기기(PC/모바일) 분석, 주간 단위
- 현업 FC 피드백 수집 (30초 이해도, 상담 질문 유용성)
- 외부 데이터 연계(HIRA, KDCA, 보험다모아 등), SFA 연동, Next Best Action — **PoC 가설 검증 이후 별도 판단**
