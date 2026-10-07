# DATA_METHODOLOGY

> 이 문서는 데이터가 무엇을 의미하고 무엇을 의미하지 않는지를 정의한다. 화면·AI 문구는 이 문서를 넘어서는 주장을 하지 않는다.

## 0. 검증 상태 (중요)

| 항목 | 상태 |
|------|------|
| API 사양 (endpoint, 파라미터, 연령 코드, 제한) | **사용자가 제공한 공식 문서 요약** 기준. 구현 환경에서 developers.naver.com 에 직접 접근할 수 없어 최신 원문과 대조하지 못함 |
| 실제 API 호출 | **미수행** (API Key 없음). Collector 는 Fixture/MockTransport 로만 검증됨 |
| §7 Smoke Test 1~3 | **미수행**. Key 발급 후 반드시 수행하고 결과를 이 문서에 기록할 것 |
| Fixture 값 | 공식 응답 구조를 따라 **직접 작성한 값**이며 실제 검색 데이터가 아님 |

## 1. Data Source — Naver DataLab 통합 검색어 트렌드

- `POST https://openapi.naver.com/v1/datalab/search` (JSON), 헤더 `X-Naver-Client-Id` / `X-Naver-Client-Secret`
- 일 1,000회 / Client ID. 조회 가능 최초일 2016-01-01.
- Application 등록 시 "데이터랩 (검색어트렌드)" API 선택 필요 (미선택 시 403).

### 1.1 수집 Parameter
| 파라미터 | 사용값 |
|---|---|
| startDate / endDate | 직전 **완결된 월** 기준 Rolling Window (예: 분석일 2026-10-07, 12개월 → 2025-10-01 ~ 2026-09-30) |
| timeUnit | `month` |
| keywordGroups | 5개 Topic 을 **한 Request** 에 (최대 5그룹, 그룹당 최대 20 keyword) |
| ages | **한 Request = 하나의 Age Code** (Response 에 연령 Dimension 이 없으므로) |
| gender | 남성 `m`, 여성 `f`, 전체는 파라미터 생략 |
| device | 생략 (전체) |

### 1.2 왜 "완결된 월"만 쓰는가
진행 중인 달은 부분 데이터라 Current 가 낮게/불안정하게 나올 수 있다. 분석일이 속한 달은 제외한다.

### 1.3 연령 코드
`3`=19~24, `4`=25~29, `5`=30~34, `6`=35~39, `7`=40~44, `8`=45~49, `9`=50~54, `10`=55~59, `11`=60+ (`1`=0~12, `2`=13~18 은 보험 상담 대상이 아니라 UI 에서 제외)

## 2. Keyword Group (topics_version = v1)
| Topic | Keywords |
|---|---|
| 암보험 | 암보험, 암진단비, 암보장 |
| 건강보험 | 건강보험, 종합건강보험 |
| 실손보험 | 실손보험, 실비보험 |
| 종신보험 | 종신보험 |
| 간병보험 | 간병보험, 간병인보험 |

정의는 `config/topics.yaml`. **Keyword 를 바꾸면 Trend 정의가 바뀐다** → `topics_version` 을 올리고 변경 이력을 파일 상단에 남긴다. Raw 와 캐시 키에 topics_version·keyword 가 포함된다.

Keyword 편향 검토 메모 (초기 예시 키워드이며 현업 검토 필요):
- "건강보험"은 국민건강보험(공적보험) 관련 검색이 섞일 가능성이 높다 → 민간 건강보험 관심으로 읽으면 안 됨.
- "암보험/암진단비/암보장"은 서로 의미가 겹치고 합산되므로 한 단어의 검색 습관이 Topic 전체를 좌우할 수 있다.
- 실손/실비 동의어, 간병보험/간병인보험 등 표현 선택에 따라 결과가 달라진다.

## 3. Raw 보존
`data/raw/naver/<YYYY-MM-DD>/age_<code>_gender_<g>_<N>m.json` = `{ "metadata": {...}, "response": <원본 그대로> }`.
metadata: requested_at, start_date, end_date, time_unit, age_codes, gender, device, topics_version, topic_groups, source.
Processed(SQLite 캐시)와 분리되며 Raw 는 수정하지 않는다. Mock 데이터는 Raw/캐시에 저장하지 않는다.

## 4. Metric (모두 **project-defined**, Naver 공식 지표 아님)
- **Current Index** = 조회 구간 마지막 월의 ratio
- **MoM %** = (Current − 전월) / 전월 × 100. 전월이 없거나 0 이하면 N/A
- **3M Average** = Current **직전** 3개월 평균 (Current 제외, 달력상 연속 3개월이 모두 있어야 함)
- **3M Momentum %** = (Current − 3M Average) / 3M Average × 100. 평균 0 이하/데이터 부족이면 N/A
- **Direction**: Momentum ≥ +5 → UP, ≤ −5 → DOWN, 사이 → STABLE, 계산 불가 → UNKNOWN (임계값은 `app_config.yaml`)
- 월이 비어 있으면 인접 월로 메우지 않는다 (전월로 간주하지 않음).

## 5. Interpretation
ratio 는 **조회 구간·조건 안에서 가장 높은 검색 수준을 100 으로 둔 상대값**이다. 허용 문구: "검색 관심지수 ▲", "3개월 평균 대비 +x%", "관심 상승". 금지: "검색량 x% 증가", "판매 증가", "수요 증가", "x%가 관심".

## 6. Limitation
- 절대 검색량이 아니다. 실제 보험 판매량·가입률이 아니다. 개인 고객의 보험 수요/필요성이 아니다.
- Keyword 선택에 따라 결과가 변한다 (§2).
- **정규화 문제**: ratio 는 Request 마다 최댓값=100 으로 재정규화된다.
  - 같은 값이어도 다른 Request(연령·성별·기간·keywordGroup 구성이 다름)의 80 과 60 은 비교할 수 없다 → "25~29세가 30~34세보다 암보험 관심이 높다" 같은 표현 금지.
  - 기간(6/12/24개월)을 바꾸면 같은 Topic 도 ratio 값이 달라질 수 있다 → 기간 변경 시 값이 아니라 방향·추세를 본다.
  - 월별 값을 서로 다른 Request 결과로 이어붙이지 않는다. 항상 같은 길이의 Window 를 한 번에 재조회한다.
- 같은 Request 안의 Topic 간 크기 비교는 공식 예시상 가능해 보이나 **실측 미확인**이고 Topic 간 인기순위는 이 도구의 목적이 아니므로, UI 는 각 Topic 의 **자기 자신 대비 변화**만 강조한다.
- 월 단위 지표라 최근 일주일의 급변은 반영되지 않는다. 최근 3개월 평균은 계절성(예: 연말정산, 건강검진 시기)을 보정하지 않는다.

## 7. 실 API 연결 시 필수 Smoke Test (미수행)
1. 25~29세 남성·12개월·5 Topic 한 Request → results 5개, period/ratio 정상.
2. 전체 results 에서 `100` 이 Topic 별로 각각 생기는지, 5개 Topic×전체 기간에서 단 하나의 최댓값인지 확인 (공식 예시는 후자를 시사).
3. 동일 조건에서 "5 Topic 한 Request" vs "Topic 별 개별 Request" 의 ratio 척도 차이 확인 → 결과에 따라 Topic 간 비교 UI 허용 여부 확정.
결과는 이 섹션에 날짜와 함께 기록한다.
