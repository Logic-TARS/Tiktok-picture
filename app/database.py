from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ensure_data_dirs


DB_PATH = DATA_DIR / "app.db"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_data_dirs()
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                material_type TEXT NOT NULL,
                material_paths TEXT NOT NULL,
                cover_path TEXT DEFAULT '',
                title TEXT DEFAULT '',
                body TEXT DEFAULT '',
                hashtags TEXT DEFAULT '[]',
                platform TEXT NOT NULL DEFAULT 'douyin',
                status TEXT NOT NULL,
                publish_mode TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                douyin_url TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_column(conn, "jobs", "platform", "TEXT NOT NULL DEFAULT 'douyin'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publish_records (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                material_type TEXT NOT NULL,
                material_paths TEXT NOT NULL,
                cover_path TEXT DEFAULT '',
                caption_text TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'douyin',
                status TEXT NOT NULL,
                published_at TEXT,
                douyin_url TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        ensure_column(conn, "publish_records", "platform", "TEXT NOT NULL DEFAULT 'douyin'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(row["name"] == column for row in rows):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["material_paths"] = json.loads(data["material_paths"])
    data["hashtags"] = json.loads(data["hashtags"] or "[]")
    return data


def create_job(
    material_paths: list[str],
    *,
    title: str = "",
    body: str = "",
    hashtags: list[str] | None = None,
    material_type: str = "image_gallery",
    cover_path: str = "",
    publish_mode: str = "semi_auto",
    status: str = "pending",
    platform: str = "douyin",
) -> dict[str, Any]:
    init_db()
    job_id = uuid.uuid4().hex[:12]
    created_at = now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, material_type, material_paths, cover_path, title, body, hashtags,
                platform, status, publish_mode, error_message, douyin_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?)
            """,
            (
                job_id,
                material_type,
                json.dumps(material_paths, ensure_ascii=False),
                cover_path,
                title,
                body,
                json.dumps(hashtags or [], ensure_ascii=False),
                platform,
                status,
                publish_mode,
                created_at,
                created_at,
            ),
        )
    return get_job(job_id)


def delete_jobs_by_status(statuses: list[str], *, material_type: str | None = None) -> int:
    init_db()
    normalized = [str(status).strip() for status in statuses if str(status).strip()]
    if not normalized:
        return 0

    where_parts = [f"status IN ({', '.join('?' for _ in normalized)})"]
    params: list[Any] = list(normalized)
    if material_type:
        where_parts.append("material_type = ?")
        params.append(material_type)

    with connect() as conn:
        cursor = conn.execute(f"DELETE FROM jobs WHERE {' AND '.join(where_parts)}", params)
        return int(cursor.rowcount or 0)


def list_jobs(limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def get_job(job_id: str) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"Job not found: {job_id}")
    return _row_to_job(row)


def delete_job(job_id: str) -> dict[str, Any]:
    init_db()
    job = get_job(job_id)
    with connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return job


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    init_db()
    allowed = {
        "cover_path",
        "title",
        "body",
        "hashtags",
        "platform",
        "status",
        "publish_mode",
        "error_message",
        "douyin_url",
    }
    updates: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "hashtags":
            value = json.dumps(value or [], ensure_ascii=False)
        updates.append(f"{key} = ?")
        params.append(value)
    updates.append("updated_at = ?")
    params.append(now_iso())
    params.append(job_id)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)
    return get_job(job_id)


def add_publish_record(job: dict[str, Any], status: str, error_message: str = "") -> None:
    record_id = uuid.uuid4().hex[:12]
    caption = build_caption_text(job)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO publish_records (
                id, job_id, material_type, material_paths, cover_path, caption_text,
                platform, status, published_at, douyin_url, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                job["id"],
                job["material_type"],
                json.dumps(job["material_paths"], ensure_ascii=False),
                job.get("cover_path", ""),
                caption,
                job.get("platform", "douyin"),
                status,
                now_iso() if status in {"submitted", "need_manual"} else None,
                job.get("douyin_url", ""),
                error_message,
                now_iso(),
            ),
        )


def build_caption_text(job: dict[str, Any]) -> str:
    hashtags = " ".join(
        tag if str(tag).startswith("#") else f"#{tag}" for tag in job.get("hashtags", [])
    )
    parts = [job.get("title", "").strip(), job.get("body", "").strip(), hashtags.strip()]
    return "\n\n".join(part for part in parts if part)


def list_records(limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM publish_records ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    records = []
    for row in rows:
        data = dict(row)
        data["material_paths"] = json.loads(data["material_paths"])
        records.append(data)
    return records


def used_material_paths() -> set[str]:
    paths: set[str] = set()
    for job in list_jobs(limit=10000):
        if job["status"] in {"need_manual", "submitted", "published"}:
            paths.update(str(Path(path)) for path in job["material_paths"])
    return paths
