"""SQLite 存储：记录每次推送、接收反馈、统计各源准确率。

一次"推送事件"对应一个地点的一次朝霞/晚霞。由于多源任一触发即推送，
我们把触发的源信息存为 JSON，并为每个触发的源单独记一条 source_hit，
这样统计准确率时能区分"哪个源报准了"。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager


SCHEMA = """
CREATE TABLE IF NOT EXISTS push_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,        -- 推送时间
    location TEXT NOT NULL,          -- 地点
    kind TEXT NOT NULL,              -- 朝霞/晚霞
    slot TEXT NOT NULL DEFAULT '',   -- 推送时段：sunrise/sunset_afternoon/sunset_pre
    event_date TEXT NOT NULL,        -- 事件日期 YYYY-MM-DD
    event_time TEXT,                 -- 日出/日落时刻
    triggered_sources TEXT,          -- JSON: 触发的源列表及理由
    feedback TEXT DEFAULT NULL,      -- 反馈：none/small/medium/large（未出现/小烧/中烧/大烧）
    feedback_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS source_hit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    push_event_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,       -- own_algo/sunsetbot/caiyun
    source_label TEXT,
    score REAL,
    raw_quality TEXT,
    reason TEXT,
    FOREIGN KEY (push_event_id) REFERENCES push_event(id)
);
"""

# 反馈等级 -> 中文标签
FEEDBACK_LABELS = {
    "none": "未出现",
    "small": "小烧",
    "medium": "中烧",
    "large": "大烧",
}
# 视为"预测命中"的反馈（出现了任何程度的烧）
HIT_FEEDBACKS = {"small", "medium", "large"}


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as c:
            c.executescript(SCHEMA)

    # ---- 写入 ----
    def record_push(self, location: str, kind: str, event_date: str,
                    event_time: str, triggered_predictions: list,
                    slot: str = "") -> int:
        """记录一次推送，triggered_predictions 是触发的 Prediction 列表。"""
        summary = [
            {"source": p.source_name, "label": p.source_label,
             "score": p.score, "reason": p.reason}
            for p in triggered_predictions
        ]
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO push_event
                   (created_at, location, kind, slot, event_date, event_time, triggered_sources)
                   VALUES (?,?,?,?,?,?,?)""",
                (dt.datetime.now().isoformat(timespec="seconds"), location, kind,
                 slot, event_date, event_time, json.dumps(summary, ensure_ascii=False)),
            )
            push_id = cur.lastrowid
            for p in triggered_predictions:
                c.execute(
                    """INSERT INTO source_hit
                       (push_event_id, source_name, source_label, score, raw_quality, reason)
                       VALUES (?,?,?,?,?,?)""",
                    (push_id, p.source_name, p.source_label, p.score, p.raw_quality, p.reason),
                )
            return push_id

    def set_feedback(self, push_id: int, feedback: str):
        if feedback not in FEEDBACK_LABELS:
            raise ValueError(f"非法反馈值: {feedback}")
        with self._conn() as c:
            c.execute(
                "UPDATE push_event SET feedback=?, feedback_at=? WHERE id=?",
                (feedback, dt.datetime.now().isoformat(timespec="seconds"), push_id),
            )

    # ---- 查询 ----
    def list_pushes(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM push_event ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def stats_by_source(self) -> list[dict]:
        """各源准确率：在有反馈的推送中，该源触发且实际出现烧的比例。"""
        with self._conn() as c:
            rows = c.execute("""
                SELECT sh.source_name, sh.source_label,
                       COUNT(*) AS total,
                       SUM(CASE WHEN pe.feedback IN ('small','medium','large') THEN 1 ELSE 0 END) AS hits
                FROM source_hit sh
                JOIN push_event pe ON pe.id = sh.push_event_id
                WHERE pe.feedback IS NOT NULL
                GROUP BY sh.source_name, sh.source_label
            """).fetchall()
            out = []
            for r in rows:
                total = r["total"] or 0
                hits = r["hits"] or 0
                out.append({
                    "source_name": r["source_name"],
                    "source_label": r["source_label"],
                    "total": total,
                    "hits": hits,
                    "accuracy": round(hits / total * 100, 1) if total else 0.0,
                })
            return out

    def has_pushed(self, location: str, kind: str, event_date: str, slot: str = "") -> bool:
        """去重：同地点同类型同事件日期同时段是否已推送过。"""
        with self._conn() as c:
            r = c.execute(
                "SELECT 1 FROM push_event WHERE location=? AND kind=? AND event_date=? AND slot=? LIMIT 1",
                (location, kind, event_date, slot),
            ).fetchone()
            return r is not None
