"""Raw 파일 저장 + SQLite 캐시.

- Raw: data/raw/naver/<YYYY-MM-DD>/age_<code>_gender_<g>_<N>m.json
  {"metadata": RequestMeta, "response": <Naver 원본 그대로>}
- Cache: 같은 조건 재호출 방지 (Naver 일 1,000회 한도 보호). Raw 응답 + metadata 를 보관.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from src.models import RequestMeta


def cache_key(meta: RequestMeta) -> str:
    payload = {
        "src": meta.source,
        "start": meta.start_date.isoformat(),
        "end": meta.end_date.isoformat(),
        "unit": meta.time_unit,
        "ages": meta.age_codes,
        "gender": meta.gender,
        "device": meta.device,
        "topics_version": meta.topics_version,
        "groups": meta.topic_groups,  # Keyword 가 바뀌면 다른 Trend 이므로 키에 포함
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Repository:
    def __init__(self, db_path: Path, raw_dir: Path):
        self.db_path = Path(db_path)
        self.raw_dir = Path(raw_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS raw_cache (
                       cache_key TEXT PRIMARY KEY,
                       fetched_at TEXT NOT NULL,
                       meta_json TEXT NOT NULL,
                       response_json TEXT NOT NULL)"""
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ---- Raw 파일 ----
    def save_raw(self, meta: RequestMeta, response: dict[str, Any]) -> Path:
        day = meta.requested_at.astimezone().strftime("%Y-%m-%d")
        months = (meta.end_date.year - meta.start_date.year) * 12 + meta.end_date.month - meta.start_date.month + 1
        age = "-".join(meta.age_codes) or "all"
        name = f"age_{age}_gender_{meta.gender or 'all'}_{months}m.json"
        path = self.raw_dir / "naver" / day / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"metadata": json.loads(meta.model_dump_json()), "response": response}, f, ensure_ascii=False, indent=2)
        return path

    # ---- SQLite 캐시 ----
    def put_cache(self, meta: RequestMeta, response: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO raw_cache VALUES (?,?,?,?)",
                (
                    cache_key(meta),
                    datetime.now(timezone.utc).isoformat(),
                    meta.model_dump_json(),
                    json.dumps(response, ensure_ascii=False),
                ),
            )

    def get_cache(self, meta: RequestMeta, ttl_hours: float) -> Optional[tuple[RequestMeta, dict[str, Any]]]:
        with self._conn() as c:
            row = c.execute(
                "SELECT fetched_at, meta_json, response_json FROM raw_cache WHERE cache_key=?", (cache_key(meta),)
            ).fetchone()
        if not row:
            return None
        fetched = datetime.fromisoformat(row[0])
        if datetime.now(timezone.utc) - fetched > timedelta(hours=ttl_hours):
            return None
        return RequestMeta.model_validate_json(row[1]), json.loads(row[2])
