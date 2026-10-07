# PROJECT_SPEC — Age Market Radar

## 1. 목적 / 가설
FC가 상담 전에 고객의 연령·성별 집단에서 최근 어떤 보험/보장 영역의 **검색 관심도**가 오르거나 내리는지 30초 안에 파악하고, 상담에서 무엇을 확인할지 생각할 수 있게 한다.

> `검색 관심도 ≠ 실제 판매량 ≠ 개인 고객에게 필요한 보험`

## 2. 하지 않는 것
상품/보험사 추천, 판매량 표현, 개인 가입 필요성 판단, 판매 유도, 근거 없는 통계 생성. (Out of scope 목록은 원 요청서 §33 준수)

## 3. MVP 기능
| # | 기능 | 비고 |
|---|------|------|
| F1 | Segment 선택 (연령 3~11 코드, 성별 남/여/전체) | 기본 25~29세 남성 |
| F2 | 5개 Topic 관심도 Trend 카드 | Current Index / MoM / 3M Momentum / Direction |
| F3 | Topic별 12개월 Line Chart | Topic 선택형 |
| F4 | AI Monthly Brief + 상담 질문(최대 3) | Optional. LLM 없으면 규칙 기반 Brief |
| F5 | Disclaimer / Mock·Real 배지 / 기준시점 | 항상 표시 |

## 4. 데이터 소스
Naver DataLab 통합검색어 트렌드 API (`POST https://openapi.naver.com/v1/datalab/search`). 명세는 `docs/DATA_METHODOLOGY.md` §1 참조 (사용자 제공 공식 문서 요약 기준).

## 5. 핵심 설계 결정
1. **한 Segment = 한 Age Code = 한 Request.** 5개 Topic을 같은 Request에 넣는다 (동일 정규화 범위).
2. **서로 다른 Request의 ratio 절대값은 비교하지 않는다.** 지표는 Topic 자기 자신의 시계열 변화(MoM, 3M Momentum)만 사용한다. Topic 간 "관심도가 더 높다" 표현 금지.
3. **조회 구간은 완결된 월만 사용**: endDate = 직전 월 말일. 진행 중인 달의 부분 데이터가 Current로 쓰이는 왜곡을 피한다.
4. **Rolling Window 재조회**: 월별 값을 이어붙이지 않고, 매번 동일 길이 윈도우 전체를 한 Request로 조회한다. (정규화 척도 변화 방지)
5. **계산은 Python, 설명만 AI.** LLM 출력은 가드레일(금칙어/필수 문구/질문 수) 검증 후 실패 시 규칙 기반 Brief로 대체.
6. **Mock Mode 기본값.** `APP_MODE=mock|real`. Mock은 화면에 `DEMO DATA` 고정 표시.

## 6. 지표 정의 (project-defined metrics, Naver 공식 지표 아님)
- Current = 윈도우의 마지막 월 ratio
- MoM% = (Current − Prev) / Prev × 100, Prev ≤ 0 → N/A
- 3M Avg = Current 직전 3개월 평균 (Current 제외). Momentum% = (Current − 3M Avg) / 3M Avg × 100
- Direction: Momentum ≥ +5 UP, ≤ −5 DOWN, 그 사이 STABLE (config), 계산 불가 시 UNKNOWN

## 7. 아키텍처
Collector → Raw(JSON 파일 + metadata) → Normalizer → Trend Calculator → SQLite 캐시 → Insight Service(Provider Adapter) → Streamlit.

## 8. 오류 처리
Timeout / 제한적 Retry(5xx, 429, timeout만, 최대 3회) / 400·401·403 즉시 실패 / 비정상 JSON → 사용자 친화 메시지. 대시보드는 Crash하지 않는다. 일 1,000회 한도 대비 SQLite 캐시(TTL 설정).

## 9. 품질 기준
Acceptance Criteria는 원 요청서 §32 그대로. 테스트: unit / fixture / integration(환경변수 있을 때만, `-m integration`).
