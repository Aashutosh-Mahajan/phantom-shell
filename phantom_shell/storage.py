from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class History:
    def __init__(self, path: Path | str):
        memory_only = str(path) == ":memory:"
        if not memory_only:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, type TEXT NOT NULL, severity TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL, answer TEXT NOT NULL)")
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(investigations)")}
        if "model_tag" not in columns:
            self.db.execute("ALTER TABLE investigations ADD COLUMN model_tag TEXT NOT NULL DEFAULT ''")
        if "duration_ms" not in columns:
            self.db.execute("ALTER TABLE investigations ADD COLUMN duration_ms INTEGER")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.commit()

    def save_event(self, event: dict[str, Any]) -> None:
        self.db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)", (event["id"], event["observed_at"], event["type"], event["severity"], json.dumps(event)))
        self.db.commit()

    def save_investigation(self, ident: str, observed_at: str, question: str, status: str, answer: str, model_tag: str = "", duration_ms: int | None = None) -> None:
        # In-place forward-compatible migration for the early scaffold database.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(investigations)")}
        if "model_tag" not in columns:
            self.db.execute("ALTER TABLE investigations ADD COLUMN model_tag TEXT NOT NULL DEFAULT ''")
        if "duration_ms" not in columns:
            self.db.execute("ALTER TABLE investigations ADD COLUMN duration_ms INTEGER")
        self.db.execute("INSERT INTO investigations (id, observed_at, question, status, answer, model_tag, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?)", (ident, observed_at, question[:1000], status, answer[:24000], model_tag[:120], duration_ms))
        self.db.commit()

    def events(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT payload FROM events ORDER BY observed_at DESC LIMIT ?", (max(1, min(limit, 100)),))
        return [json.loads(row[0]) for row in rows]

    def prune(self, retention_days: int) -> None:
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650")
        self.db.execute("DELETE FROM events WHERE julianday(observed_at) < julianday('now', ?)", (f"-{retention_days} days",))
        self.db.execute("DELETE FROM investigations WHERE julianday(observed_at) < julianday('now', ?)", (f"-{retention_days} days",))
        self.db.commit()

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT payload FROM events WHERE id=?", (event_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def search_events(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        term = f"%{query[:100]}%"
        rows = self.db.execute("SELECT payload FROM events WHERE type LIKE ? OR severity LIKE ? OR payload LIKE ? ORDER BY observed_at DESC LIMIT ?", (term, term, term, max(1, min(limit, 30))))
        return [json.loads(row[0]) for row in rows]

    def investigations(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT id, observed_at, question, status, model_tag, duration_ms, answer FROM investigations ORDER BY observed_at DESC LIMIT ?", (max(1, min(limit, 100)),))
        return [{"id": r[0], "observed_at": r[1], "question": r[2], "status": r[3], "model_tag": r[4], "duration_ms": r[5], "answer": r[6]} for r in rows]

    def get_investigation(self, investigation_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT id, observed_at, question, status, model_tag, duration_ms, answer FROM investigations WHERE id=?", (investigation_id,)).fetchone()
        return {"id": row[0], "observed_at": row[1], "question": row[2], "status": row[3], "model_tag": row[4], "duration_ms": row[5], "answer": row[6]} if row else None

    def set_setting(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key[:100], json.dumps(value)))
        self.db.commit()

    def get_settings(self) -> dict[str, Any]:
        return {key: json.loads(value) for key, value in self.db.execute("SELECT key,value FROM settings")}

    def close(self) -> None:
        self.db.close()

    def clear(self) -> None:
        self.db.execute("DELETE FROM events")
        self.db.execute("DELETE FROM investigations")
        self.db.execute("DELETE FROM settings")
        self.db.commit()
