"""Append-only local snapshots. The source input and rubric version travel with each result."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def database_path() -> Path:
    root = os.environ.get("GEMS_STATE_DIR")
    if root:
        return Path(root).expanduser() / "analyses.sqlite3"
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
    return base / "gems-research" / "analyses.sqlite3"


def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL, result TEXT NOT NULL)")
    return connection


def save(data: dict, result: dict) -> str:
    key = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
                   (key, datetime.now(timezone.utc).isoformat(), data["symbol"],
                    json.dumps(data, ensure_ascii=False), json.dumps(result, ensure_ascii=False)))
    return key


def history() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT id, created_at, symbol, result FROM analyses ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(id=row["id"], created_at=row["created_at"], symbol=row["symbol"],
                 **{k: v for k, v in json.loads(row["result"]).items() if k in {"name", "score", "coverage", "rubric_version", "demo"}}) for row in rows]


def get(key: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM analyses WHERE id = ?", (key,)).fetchone()
    return dict(id=row["id"], payload=json.loads(row["payload"]), result=json.loads(row["result"])) if row else None
