# memory.py — JARVIS SQLite three-tier memory system
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/jarvis.db")
MAX_RECENT = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, content=messages, content_rowid=id
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TABLE IF NOT EXISTS facts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fact    TEXT NOT NULL UNIQUE,
    ts      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    status  TEXT NOT NULL DEFAULT 'pending',
    ts      REAL NOT NULL
);
"""


class Memory:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.recent: list[dict] = self._hydrate_recent()

    def _hydrate_recent(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (MAX_RECENT,),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    # --- recent tier ---

    def add_exchange(self, role: str, content: str) -> None:
        self.recent.append({"role": role, "content": content})
        if len(self.recent) > MAX_RECENT:
            self.recent = self.recent[-MAX_RECENT:]
        self.conn.execute(
            "INSERT INTO messages (role, content, ts) VALUES (?,?,?)",
            (role, content, time.time()),
        )
        self.conn.commit()

    def get_recent(self) -> list[dict]:
        return list(self.recent)

    def clear_recent(self) -> None:
        self.recent = []

    # --- facts tier ---

    def add_fact(self, fact: str) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO facts (fact, ts) VALUES (?,?)",
            (fact, time.time()),
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = self.conn.execute("SELECT id FROM facts WHERE fact=?", (fact,)).fetchone()
        return row[0] if row else -1

    def delete_fact(self, fact_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_facts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, fact, ts FROM facts ORDER BY ts DESC"
        ).fetchall()
        return [{"id": r[0], "fact": r[1], "ts": r[2]} for r in rows]

    def facts_as_context(self) -> str:
        facts = self.list_facts()
        if not facts:
            return ""
        lines = "\n".join(f"- {f['fact']}" for f in facts)
        return f"Known facts about the user:\n{lines}"

    # --- FTS search ---

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            """SELECT m.id, m.role, m.content, m.ts
               FROM messages_fts fts
               JOIN messages m ON fts.rowid = m.id
               WHERE messages_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "ts": r[3]} for r in rows]

    # --- tasks ---

    def add_task(self, title: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks (title, status, ts) VALUES (?,?,?)",
            (title, "pending", time.time()),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_task_status(self, task_id: int, status: str) -> bool:
        cur = self.conn.execute(
            "UPDATE tasks SET status=? WHERE id=?", (status, task_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT id, title, status, ts FROM tasks WHERE status=? ORDER BY ts DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, title, status, ts FROM tasks ORDER BY ts DESC"
            ).fetchall()
        return [{"id": r[0], "title": r[1], "status": r[2], "ts": r[3]} for r in rows]
