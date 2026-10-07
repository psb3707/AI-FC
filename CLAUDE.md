# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Windows; a `.venv` exists in the repo root (Python 3.14, spec requires 3.12+). The Bash tool's PATH may not see `python`, so call the venv interpreter directly.

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py            # dashboard (APP_MODE=mock by default)
.venv\Scripts\python -m pytest                           # unit + fixture tests; integration is excluded by default
.venv\Scripts\python -m pytest tests/unit/test_trend_calculator.py::test_classify_thresholds   # single test
.venv\Scripts\python -m pytest -m integration            # real Naver API call; skips without NAVER_CLIENT_ID/SECRET
```

No linter/formatter is configured. `pytest.ini` sets `pythonpath = .` (imports are `from src...`) and `addopts = -m "not integration"`.

When printing Korean from scripts on this machine, set `PYTHONUTF8=1` (console is cp949).

## Product constraints that shape the code

The tool shows *search interest* trends per age/gender segment for FCs (insurance agents). It must never present them as search volume, sales, or an individual's insurance need, and must never recommend products. These rules are enforced in code, not just copy:

- UI/AI wording says "검색 관심지수/관심도", never "검색량 +x%". `src/insights/guardrails.py` rejects forbidden phrases, "검색량 …증가"-style claims, missing disclaimer text, and >3 questions.
- Numbers are computed only in `src/processing/trend_calculator.py`. The LLM receives `build_payload()` output (computed metrics only, never the raw Naver response) and only explains it.
- Mock data must always show the `DEMO DATA` banner and is never written to `data/raw` or the SQLite cache.

## Architecture (read across files)

Flow: `ReportService.get_report` (`src/service.py`) → Collector or mock generator → raw JSON + SQLite cache (`src/storage/repository.py`) → `normalizer.normalize` → `trend_calculator.compute_metrics` → `SegmentReport` (`src/models.py`) → `app.py` renders cards/chart and calls an `InsightProvider`.

Non-obvious design decisions (details in `docs/DATA_METHODOLOGY.md`, diagram in `docs/ARCHITECTURE.md`):

- **Naver `ratio` is relative to each request's max (=100).** Values from different requests (age, gender, period, keyword set) are not comparable. Hence: one request = one segment = one age code (`ages=[code]`), all 5 topics in the same request, and metrics are only self-vs-own-history (MoM, 3M momentum). Never splice months from different requests; always re-query the full rolling window.
- **Window uses only complete months**: `service.window()` ends at the last day of the previous month, so a partial current month never becomes "Current".
- **Metric semantics**: 3M average excludes the current month and requires 3 consecutive calendar months present (gaps are not filled and a missing prior month is not treated as "previous"). Unavailable values become `None` with `Direction.UNKNOWN`, never exceptions.
- **Errors never crash the UI**: `ReportService` converts `CollectorError`, `MalformedResponseError`, and anything else into `SegmentReport.error` (a user-facing Korean message). Collector retries only 5xx/429/timeouts (max `max_retries` total attempts); other 4xx fail immediately.
- **Cache key** (`repository.cache_key`) includes dates, age, gender, `topics_version`, and the keyword groups, so editing `config/topics.yaml` invalidates cache. Bump `topics_version` whenever keywords change.
- **Insight providers** (`src/insights/`): `get_provider()` returns the OpenAI provider only if `OPENAI_API_KEY` is set and `ai.enabled`; otherwise the rule-based `TemplateInsightProvider`. `OpenAIInsightProvider` falls back to the template on HTTP errors or guardrail violations. The core dashboard must work with no LLM.
- Topics, thresholds, cache TTL, periods and defaults live in `config/*.yaml` (validated in `src/config.py`; max 5 topics / 20 keywords per topic per Naver limits). Don't hard-code topics in code.
- Age codes in `src/models.AGE_CODES` are Naver's official `ages` codes (3=19~24 … 11=60+).

## Status caveats

The Naver API spec was taken from a document the user pasted (developers.naver.com was unreachable from the tooling), and the real API has not been called yet (no keys). `tests/fixtures/naver_datalab_response.json` is hand-written, not real data. The Smoke Tests in `docs/DATA_METHODOLOGY.md` §7 are still to be run once keys exist.

## Secrets

`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `OPENAI_API_KEY`, `APP_MODE` come from `.env` (loaded in `app.py` and the integration test); see `.env.example`.
