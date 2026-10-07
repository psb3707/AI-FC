"""FC Age Market Radar — Streamlit Dashboard."""
from __future__ import annotations

import json
import logging

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.config import ROOT, app_mode, load_app_config, load_topics, ConfigError
from src.chart_data import topic_chart_frame
from src.insights import build_payload, get_provider
from src.insights.base import GENERIC_DEEP_DIVE_QUESTION, GENERIC_VALIDATION_QUESTION, Brief
from src.insights.signals import build_consult_prep
from src.models import AGE_CODES, GENDERS, Direction, Segment
from src.service import ReportService
from src.storage.repository import Repository

load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, filename=ROOT / "app.log", encoding="utf-8")

st.set_page_config(page_title="FC Age Market Radar", page_icon="📡", layout="wide")

DISCLAIMER = (
    "본 데이터는 **검색 관심도의 상대적 변화**를 나타내며 실제 보험상품 판매량 또는 해당 고객에게 필요한 보험을 의미하지 않습니다.  \n"
    "개별 고객에 대한 보험 제안은 고객의 실제 건강상태, 보유계약, 재무상황 및 보험 니즈를 확인한 후 수행해야 합니다."
)
DISCLAIMER_SHORT = "※ 본 지표는 검색 관심도의 상대적 변화이며 실제 판매량 또는 개별 고객의 보험 필요성을 의미하지 않습니다."
SFA_NOTE = (
    "본 화면은 개별 고객의 보험 추천을 위한 화면이 아니라 상담 전 고객군별 시장 Signal을 파악하기 위한 참고 도구입니다.  \n"
    "실제 고객 니즈와 보험 적합성은 고객 조회 및 상담 단계에서 별도로 확인해야 합니다."
)
ARROW = {Direction.UP: "↑", Direction.DOWN: "↓", Direction.STABLE: "→", Direction.UNKNOWN: "–"}
DIR_TEXT = {Direction.UP: "관심 상승", Direction.DOWN: "관심 하락", Direction.STABLE: "큰 변화 없음", Direction.UNKNOWN: "판단 불가"}
DIR_COLOR = {Direction.UP: "red", Direction.DOWN: "blue", Direction.STABLE: "gray", Direction.UNKNOWN: "gray"}
CIRCLED = "①②③④⑤"


@st.cache_resource
def get_context():
    topics, cfg = load_topics(), load_app_config()
    repo = Repository(ROOT / "data" / "processed" / "cache.sqlite3", ROOT / "data" / "raw")
    mode = app_mode()
    return topics, cfg, ReportService.from_env(mode, topics, cfg, repo), get_provider(cfg), mode


@st.cache_data(show_spinner=False)
def make_brief(payload_json: str, _provider, provider_name: str) -> Brief:
    return _provider.generate(json.loads(payload_json))


def fmt_pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v:+.1f}%"


try:
    topics, cfg, service, provider, mode = get_context()
except ConfigError as e:
    st.error(f"설정 파일 오류로 실행할 수 없습니다: {e}")
    st.stop()

# ---------------- Header ----------------
st.title("FC Age Market Radar")
st.caption("상담 전, 고객군의 보험 관심 변화에서 무엇을 먼저 물어볼지 가설을 세우는 도구")
badge_slot = st.empty()  # 데이터 기준월은 조회 후 채운다

if mode == "mock":
    st.error("🧪 **DEMO DATA** — 가상으로 생성한 데모 데이터입니다. 실제 검색 데이터가 아니며 상담에 활용할 수 없습니다.", icon="🚨")
st.caption(DISCLAIMER_SHORT)

# ---------------- Filters ----------------
c1, c2, c3 = st.columns([2, 2, 2])
age_codes = list(AGE_CODES)
default_age = age_codes.index(cfg.defaults.age_code) if cfg.defaults.age_code in age_codes else 1
with c1:
    age_code = st.selectbox("Age Group", age_codes, index=default_age, format_func=lambda c: AGE_CODES[c] + ("" if c == "11" else "세"))
with c2:
    gender = st.radio("Gender", list(GENDERS), index=list(GENDERS).index(cfg.defaults.gender), format_func=lambda g: GENDERS[g][0], horizontal=True)
with c3:
    opts = cfg.periods.options
    months = st.selectbox("Period", opts, index=opts.index(cfg.periods.default) if cfg.periods.default in opts else 0, format_func=lambda m: f"최근 {m}개월")

segment = Segment(age_code=age_code, gender=gender)
with st.spinner("관심도 데이터를 불러오는 중..."):
    report = service.get_report(segment, months)

if report.error:
    st.error(report.error)
    st.stop()

# ---------------- 데이터 출처 Badge ----------------
cur = report.metrics[0].current_period
if report.data_source == "mock":
    src_badges = ":red-badge[DEMO DATA] :gray-badge[가상 데이터]"
else:
    src_badges = ":green-badge[실데이터] :blue-badge[NAVER DATALAB]"
badge_slot.markdown(
    f"{src_badges} :gray-badge[기준월 {cur:%Y-%m}]" + (" :gray-badge[캐시된 응답]" if report.from_cache else "")
)

prep = build_consult_prep(report, topics)
payload = build_payload(report, topics)
brief = make_brief(json.dumps(payload, ensure_ascii=False, sort_keys=True), provider, provider.name)

# ---------------- 이번 달 상담 준비 ----------------
st.subheader(f"{segment.label} · 이번 달 상담 준비")
with st.container(border=True):
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**이번 달 주목 Signal**")
        if prep.headline:
            for i, sg in enumerate(prep.headline):
                st.markdown(
                    f"{CIRCLED[i]} **{sg.topic}** :{DIR_COLOR[sg.direction]}[{ARROW[sg.direction]} {DIR_TEXT[sg.direction]}]  \n"
                    f"&nbsp;&nbsp;&nbsp;&nbsp;최근 3개월 평균 대비 {fmt_pct(sg.momentum_pct)}"
                )
        else:
            st.markdown("뚜렷하게 오르거나 내린 영역이 없습니다.")
        if prep.stable_topics:
            st.markdown(f":gray[· 나머지 보장 영역: 큰 변화 없음 ({', '.join(prep.stable_topics)})]")
        if prep.broad_move:
            st.caption(f"ℹ️ 여러 Topic이 함께 {DIR_TEXT[prep.broad_move]} 방향입니다. 특정 보장 영역의 변화로 읽기에는 신중하게 해석해 주세요.")
        for sg in prep.reference:
            st.caption(f"참고(헤드라인 제외) · {sg.topic}: {sg.caution}")
    with right:
        st.markdown("**FC Check Point**")
        st.write(prep.check_point or "뚜렷한 상승 Signal이 없습니다. 시장 Signal보다 고객의 현재 상황을 먼저 확인해 보세요.")
        st.markdown("**상담 시작 질문**")
        st.write(f"“{prep.validation_question or GENERIC_VALIDATION_QUESTION}”")
        st.caption(f"고객이 관심을 보인다면 → “{prep.deep_dive_question or GENERIC_DEEP_DIVE_QUESTION}”")
    st.caption("시장 데이터로 무엇을 먼저 물어볼지 가설을 세우고, 실제 니즈는 고객 상담을 통해 확인합니다.")

# ---------------- Trend Cards ----------------
st.subheader("Topic별 관심 변화")
cols = st.columns(len(report.metrics))
for col, m in zip(cols, report.metrics):
    with col, st.container(border=True):
        st.markdown(f"**{m.display_name}**")
        st.markdown(f"### :{DIR_COLOR[m.direction]}[{ARROW[m.direction]} {DIR_TEXT[m.direction]}]")
        st.caption("최근 3개월 평균 대비")
        st.markdown(f"**{fmt_pct(m.momentum_pct)}**")
        st.caption("전월 대비")
        st.markdown(f"**{fmt_pct(m.mom_pct)}**")
        if m.rises is not None:
            st.caption(f"최근 {m.rise_window}개월 중 상승 {m.rises}회")
        tp = topics.by_display_name(m.display_name)
        if tp and tp.caution:
            st.caption(f"⚠️ {tp.caution}")
        if m.note:
            st.caption(f"ℹ️ {m.note}")
st.caption("※ Topic끼리 지수의 크기를 비교하지 마세요. 각 Topic이 자기 과거 대비 어떻게 변했는지만 의미가 있습니다.")

with st.expander("상세 지표 (Raw 검색 관심지수)"):
    st.caption("검색 관심지수는 한 번의 조회 안에서 가장 높은 값을 100으로 둔 상대값입니다. Topic 간 크기 비교용이 아닙니다.")
    st.dataframe(
        pd.DataFrame([
            {"Topic": m.display_name, "현재 관심지수": m.current_index, "직전 3개월 평균": m.three_month_avg,
             "3M Momentum(%)": m.momentum_pct, "MoM(%)": m.mom_pct, "Direction": m.direction.value}
            for m in report.metrics
        ]),
        hide_index=True,
    )

# ---------------- Trend Evidence ----------------
st.subheader("왜 이렇게 판단했나 · 관심도 추이")
metric_by_name = {m.display_name: m for m in report.metrics}
default_topic = (prep.focus.topic if prep.focus else (prep.headline[0].topic if prep.headline else report.metrics[0].display_name))
names = [m.display_name for m in report.metrics]
sel = st.selectbox("Topic", names, index=names.index(default_topic))
sel_metric = metric_by_name[sel]
sel_topic = topics.by_display_name(sel)
frame = topic_chart_frame(report.records, sel_topic.id, sel_metric, cfg.trend.baseline_months)
if frame.empty:
    st.info("표시할 추이 데이터가 없습니다.")
else:
    ROLE_COLORS = alt.Scale(domain=["other", "baseline", "current"], range=["#9aa0a6", "#f4a261", "#d62828"])
    line = alt.Chart(frame).mark_line(color="#9aa0a6").encode(
        x=alt.X("period:T", title="월", axis=alt.Axis(format="%Y-%m", labelAngle=-45, values=[pd.Timestamp(d).isoformat() for d in frame["period"]])),
        y=alt.Y("ratio:Q", title="검색 관심지수 (상대값)"),
    )
    pts = alt.Chart(frame).mark_point(filled=True, size=90).encode(
        x="period:T", y="ratio:Q",
        color=alt.Color("role:N", scale=ROLE_COLORS, legend=None),
        tooltip=[alt.Tooltip("period:T", title="월", format="%Y-%m"), alt.Tooltip("ratio:Q", title="관심지수", format=".1f")],
    )
    layers = [line, pts]
    base = frame[frame["role"] == "baseline"]
    if sel_metric.three_month_avg is not None and not base.empty:
        rule_df = pd.DataFrame({"x1": [base["period"].min()], "x2": [frame[frame["role"] == "current"]["period"].max()], "y": [sel_metric.three_month_avg]})
        layers.append(alt.Chart(rule_df).mark_rule(strokeDash=[6, 4], color="#f4a261", size=2).encode(x="x1:T", x2="x2:T", y="y:Q"))
    st.altair_chart(alt.layer(*layers).properties(height=320), width="stretch")
    if sel_metric.three_month_avg is not None:
        st.caption(
            f"🟠 주황 점 = 직전 3개월, 점선 = 그 평균({sel_metric.three_month_avg:.1f}) · 🔴 빨간 점 = 현재({cur:%Y-%m}, {sel_metric.current_index}). "
            f"현재가 평균 대비 {fmt_pct(sel_metric.momentum_pct)} → {DIR_TEXT[sel_metric.direction]}으로 분류했습니다. "
            f"(기준: ±{cfg.trend.up_threshold_pct:.0f}%)"
        )
    else:
        st.caption("직전 3개월 데이터가 부족해 평균 대비 변화를 계산하지 못했습니다.")
if sel_topic.caution:
    st.warning(sel_topic.caution, icon="⚠️")

# ---------------- AI Interpretation ----------------
st.subheader("AI 해석")
badge = ":blue-badge[AI 생성]" if brief.provider == "openai" else ":gray-badge[규칙 기반 요약 · LLM 미사용]"
st.markdown(badge + (" :red-badge[DEMO DATA 기반]" if report.data_source == "mock" else ""))
a1, a2, a3 = st.columns(3)
with a1, st.container(border=True):
    st.markdown("**① 무엇이 변했나** · What changed")
    st.write(brief.what_changed)
with a2, st.container(border=True):
    st.markdown("**② 어떻게 해석하나** · How to interpret")
    st.write(brief.interpretation)
with a3, st.container(border=True):
    st.markdown("**③ 무엇을 물어볼까** · What to ask")
    st.caption("A. Signal 확인 질문")
    for q in brief.validation_questions:
        st.markdown(f"- {q}")
    st.caption("B. 관심을 보이면 더 묻기")
    for q in brief.deep_dive_questions:
        st.markdown(f"- {q}")
if brief.note:
    st.caption(f"ℹ️ {brief.note}")

# ---------------- SFA 역할 구분 / Methodology ----------------
st.info(SFA_NOTE + "  \n**Market Radar** → 상담 가설 · **SFA** → 개인 고객 검증 및 업무수행", icon="🧭")

with st.expander("데이터 출처 · 방법론 · 한계"):
    st.markdown(DISCLAIMER)
    src_label = "DEMO DATA" if report.data_source == "mock" else "네이버 데이터랩"
    st.caption(
        f"출처: {src_label} · 조회구간 {report.meta.start_date} ~ {report.meta.end_date}(완결된 월 기준) · "
        f"조회시각 {report.meta.requested_at.astimezone():%Y-%m-%d %H:%M}"
    )
    st.markdown(
        "- **Current**: 조회구간 마지막 월의 검색 관심지수\n"
        "- **MoM** = (Current − 전월) / 전월 × 100 (전월이 0 이하이면 N/A)\n"
        "- **3M Momentum** = (Current − 직전 3개월 평균) / 직전 3개월 평균 × 100\n"
        f"- **Direction**: Momentum ≥ {cfg.trend.up_threshold_pct:+.0f}% 상승 / ≤ {cfg.trend.down_threshold_pct:+.0f}% 하락 / 그 사이 큰 변화 없음\n"
        "- MoM·Momentum·Direction은 프로젝트 자체 정의 지표이며 Naver 공식 지표가 아닙니다.\n"
        "- 검색어 의미가 섞일 수 있는 Topic은 헤드라인 Signal에서 제외하고 참고로만 표시합니다."
    )
    st.json(json.loads(report.meta.model_dump_json()))
