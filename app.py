"""FC Age Market Radar — Streamlit Dashboard."""
from __future__ import annotations

import json
import logging

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.config import ROOT, app_mode, load_app_config, load_topics, ConfigError
from src.insights import build_payload, get_provider
from src.insights.base import Brief
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
ARROW = {Direction.UP: "▲", Direction.DOWN: "▼", Direction.STABLE: "→", Direction.UNKNOWN: "–"}
DIR_TEXT = {Direction.UP: "관심 상승", Direction.DOWN: "관심 하락", Direction.STABLE: "유지", Direction.UNKNOWN: "판단 불가"}


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
st.caption("연령·성별 고객군별 보험 관심 변화 모니터링")

if mode == "mock":
    st.error("🧪 **DEMO DATA** — 가상으로 생성한 데모 데이터입니다. 실제 검색 데이터가 아니며 상담에 활용할 수 없습니다.", icon="🚨")
else:
    st.success("실데이터 · 네이버 데이터랩 통합검색어 트렌드 (검색 관심도의 상대값)", icon="✅")
st.warning(DISCLAIMER, icon="⚠️")

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

st.subheader(f"{segment.label} · 보험 관심도 변화")

if report.error:
    st.error(report.error)
    st.stop()

# ---------------- 기준시점 ----------------
cur = report.metrics[0].current_period
src_label = "DEMO DATA" if report.data_source == "mock" else "네이버 데이터랩"
cache_note = " · 캐시된 응답" if report.from_cache else ""
st.caption(
    f"데이터 기준월: **{cur:%Y-%m}** (완결된 월 기준) · 조회구간 {report.meta.start_date} ~ {report.meta.end_date} · "
    f"출처: {src_label}{cache_note} · 조회시각 {report.meta.requested_at.astimezone():%Y-%m-%d %H:%M}"
)

# ---------------- Trend Cards ----------------
cols = st.columns(len(report.metrics))
for col, m in zip(cols, report.metrics):
    with col, st.container(border=True):
        st.markdown(f"**{m.display_name}**")
        st.markdown(f"### {ARROW[m.direction]} {fmt_pct(m.momentum_pct)}")
        st.caption(f"{DIR_TEXT[m.direction]} · 3개월 평균 대비")
        st.write(f"검색 관심지수: **{m.current_index if m.current_index is not None else 'N/A'}**")
        st.write(f"전월 대비: **{fmt_pct(m.mom_pct)}**")
        if m.note:
            st.caption(f"ℹ️ {m.note}")
st.caption("※ 검색 관심지수는 조회구간 내 최고 수준을 100으로 둔 상대값입니다. Topic 간 크기 비교보다 각 Topic의 변화 방향을 확인하세요.")

# ---------------- Trend Chart ----------------
st.subheader("관심도 추이")
df = pd.DataFrame([r.model_dump() for r in report.records])
names = {t.id: t.display_name for t in topics.topics}
df["Topic"] = df["topic"].map(names)
ranked = sorted((m for m in report.metrics if m.momentum_pct is not None), key=lambda m: abs(m.momentum_pct), reverse=True)
default_sel = [ranked[0].display_name] if ranked else [report.metrics[0].display_name]
sel = st.multiselect("Topic 선택", [m.display_name for m in report.metrics], default=default_sel)
if sel:
    pivot = df[df["Topic"].isin(sel)].pivot_table(index="period", columns="Topic", values="ratio")
    st.line_chart(pivot, y_label="검색 관심지수 (상대값)", x_label="월")
else:
    st.info("차트에 표시할 Topic을 선택해 주세요.")

# ---------------- AI Monthly Brief ----------------
st.subheader("AI Monthly Brief")
payload = build_payload(report)
brief = make_brief(json.dumps(payload, ensure_ascii=False, sort_keys=True), provider, provider.name)
badge = "🤖 AI 생성 요약" if brief.provider == "openai" else "📋 규칙 기반 요약 (LLM 미사용)"
st.caption(badge + (" · DEMO DATA 기반" if report.data_source == "mock" else ""))
st.info(brief.summary)
if brief.note:
    st.caption(f"ℹ️ {brief.note}")
st.markdown("**상담 시 확인해볼 질문**")
for q in brief.questions:
    st.markdown(f"- {q}")

# ---------------- Details ----------------
with st.expander("지표 정의 및 조회 조건"):
    st.markdown(
        "- **Current**: 조회구간 마지막 월의 검색 관심지수\n"
        "- **MoM** = (Current − 전월) / 전월 × 100 (전월이 0 이하이면 N/A)\n"
        "- **3M Momentum** = (Current − 직전 3개월 평균) / 직전 3개월 평균 × 100\n"
        f"- **Direction**: Momentum ≥ {cfg.trend.up_threshold_pct:+.0f}% 상승 / ≤ {cfg.trend.down_threshold_pct:+.0f}% 하락 / 그 사이 유지\n"
        "- MoM·Momentum·Direction은 프로젝트 자체 정의 지표이며 Naver 공식 지표가 아닙니다."
    )
    st.dataframe(pd.DataFrame([m.model_dump(mode="json") for m in report.metrics]), hide_index=True)
    st.json(json.loads(report.meta.model_dump_json()))
