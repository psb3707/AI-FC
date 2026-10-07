# PRODUCT REVIEW — Action-First 개선 (2026-10-07)

> 아래 평가는 **개발자(AI)의 자체 평가**이며 실제 FC 사용자 테스트가 아니다. 현업 검증은 ROADMAP 항목.

## 1. 검증 요약
| 구분 | 결과 |
|---|---|
| Automated (pytest) | 133 passed (기존 79 유지·갱신 + Signal/지속성/가드레일/차트 데이터/Streamlit AppTest 신규) |
| Functional(UI) | Age 9종 × Gender 3종, Period 6/12/24, Topic 5종 전환 모두 예외 없음 (AppTest, mock) |
| 실데이터 Scenario | 25~29 남 / 40~44 남 / 40~44 여 3/3 PASS (DATA_METHODOLOGY §10) |
| Keyword 민감도 | 건강보험 Direction 이 3개 Segment 모두 변경 → DATA QUALITY WARNING (§8) |
| 화면 확인 | Chrome DevTools Protocol 로 실제 렌더링 캡처 후 육안 확인 (차트 x축 중복 눈금 발견·수정) |
| 미검증 | OpenAI 실호출, 실제 FC 사용자 테스트 |

## 2. UX Self Review
**PERSONA 1 — 신입 FC · Score 4/5**
- Strength: 제목 아래 첫 블록(주목 Signal / Check Point / 시작 질문)만 읽으면 "무엇을 물어볼지"가 나온다. Raw 지수가 카드에서 사라져 숫자 해석 부담이 줄었다.
- Problem: 상승 Signal 이 없는 Segment(예: 25~29 남, 40~44 여)는 질문이 일반 질문으로 대체되어 가치가 약하다.
- Improvement: 하락 위주일 때 "먼저 꺼내지 않아도 되는 영역"을 명시하는 문구, 또는 Segment 고유 질문 은행(Roadmap).

**PERSONA 2 — 경력 FC · Score 3/5**
- Strength: 3M 평균선이 있는 차트로 "왜 +7.1% 인가"를 눈으로 확인할 수 있다. 지속성(최근 6개월 중 상승 횟수)이 단발 변동을 구분하게 돕는다.
- Problem: 새로운 정보량은 한 달 스냅샷 + 5개 Topic 으로 제한적이다. 건강보험이 경고로 제외되어 핵심 Topic 하나가 비어 있다.
- Improvement: 12개월 이상 이력(계절성), Keyword 재설계, 연령 인접 구간 비교.

**PERSONA 3 — SFA 기획/관리자 · Score 4/5**
- Strength: 니즈를 단정하지 않는 문구(가설), 가드레일(상품 추천·검색량·판매량·원인·니즈 단정·근거 없는 수치 차단), SFA 와 역할 구분 문구를 화면에 명시했다. 개인 고객 데이터를 쓰지 않아 SFA 와 기능 중복이 없다.
- Problem: "관심 상승 → 이것부터 물어보라"는 구조 자체가 암묵적으로 수요 추론으로 읽힐 위험이 남는다. 질문 은행은 사람이 쓴 것이라 현업·컴플라이언스 검토가 필요하다.
- Improvement: 질문 은행 컴플라이언스 검토, 사용 로그로 질문 유용성 측정 후 Market Intelligence 모듈 확장 여부 판단.

## 3. Product Value Validation
| Q | 판정 | 근거 / 한계 |
|---|---|---|
| Q1 30초 안에 주목할 대상 파악 | PASS | 헤드라인 Signal 이 필터 바로 아래, 방향+3M 값만 표시 |
| Q2 30초 안에 무엇을 물을지 파악 | PARTIAL | 상승 Signal 이 있으면 Topic 연결 질문(PASS). 없으면 일반 질문 — 시장 Signal 과 연결되지 않음 (3개 Scenario 중 2개) |
| Q3 검색 Trend ↔ 실제 Need 혼동 | LOW RISK | "가설", 면책 요약 상시 노출, 시작 질문은 "계기/걱정이 있으신가요" 형태. 다만 "관심 상승" 라벨만 보면 수요로 오독할 여지는 남음 |
| Q4 Raw Index 과강조 | PASS | 카드에서 제거, 상세 지표 expander + Topic 간 비교 금지 문구. 차트 y축은 선택 Topic 단일 시계열 |
| Q5 AI Brief 가 Metric 반복 | PARTIAL | What changed 는 설계상 수치를 인용(사실 단계). 해석·질문은 분리됐지만 규칙 기반 문장이 정형적이다. LLM 사용 시 개선 여지(미검증) |
| Q6 근거 없는 원인 생성 | PASS | 가드레일이 원인/니즈/위험 단정·payload 에 없는 % 수치를 차단, LLM 은 fallback. 규칙 기반 경로는 실데이터 3개로 확인 |
| Q7 사용 안 하는 것보다 쉬워졌나 | LIKELY | 질문 문장을 직접 만들 필요가 없고 근거 차트가 있음. 실제 FC 로 검증되지 않음 |

명백한 FAIL 은 없음. PARTIAL 2건은 아래 한계에 기록.

## 4. 발견 후 수정한 문제 (IMPLEMENT → TEST → REVIEW → FIX → RETEST)
1. **차트 x축 월 라벨 중복·마지막 월 누락** (스크린샷에서 발견) → 월 단위 눈금 고정.
2. **"건강보험는"** 조사 오류 → "건강보험 항목은".
3. **3개 이상 Topic 이 동시 하락**(실데이터 2/3 Scenario)인데 특정 영역 변화처럼 읽힘 → `broad_move` 플래그, UI·Brief 에 신중 해석 안내.
4. **가드레일 과잉 차단**: 스펙 질문("치료로 인해 …")이 원인 단정 패턴에 걸림 → 원인/니즈 패턴은 사실·해석 문장에만 적용.
5. **설정 로더가 신규 Topic 필드(caution/질문)를 버림** → 테스트가 잡아 수정.
6. 경고 문구 "신중이 필요합니다"가 자체 가드레일("필요합니다")에 걸림 → 문구 수정.
7. Streamlit `use_container_width` deprecation → `width="stretch"`.

## 5. 남은 한계
- 한 달 스냅샷 + 임계값 ±5% 는 임의 설정. 소폭 변동도 UP/DOWN 이 될 수 있다(지속성 지표로 보완).
- 상승 Signal 이 없을 때 질문이 일반적 (Q2 PARTIAL).
- 건강보험 Topic 은 Keyword 문제로 해석 제외 — 현업 검토 후 재설계 필요.
- 주간 상세 보기 미구현(Monthly 우선 원칙). 계절성 보정 없음.
- OpenAI 경로 실호출 미검증. 가드레일은 방향(상승/하락) ↔ 문장 일치를 의미 수준에서 검사하지 못한다(수치·표현만 검사).
- 질문 은행은 코드 리뷰 수준 검증. 실제 상담 적합성·컴플라이언스는 현업 검토 필요.
