from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath
from typing import Iterable

from app.config import DATA_DIR, ensure_data_dirs


UPLOADS_DIR = DATA_DIR / "uploads"


def ensure_uploads_dir() -> None:
    ensure_data_dirs()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_relative_filename(filename: str) -> Path:
    normalized = filename.replace("\\", "/").strip().lstrip("/")
    pure_path = PurePosixPath(normalized)
    safe_parts = [part for part in pure_path.parts if part not in {"", ".", ".."}]
    if not safe_parts:
        safe_parts = [f"file-{uuid.uuid4().hex[:8]}"]
    return Path(*safe_parts)


def save_uploaded_files(files: Iterable[tuple[str, bytes]]) -> dict[str, str | int]:
    ensure_uploads_dir()
    upload_id = uuid.uuid4().hex[:12]
    target_dir = UPLOADS_DIR / upload_id
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_count = _write_uploaded_files(files, target_dir)

    return {
        "upload_id": upload_id,
        "upload_dir": str(target_dir.resolve()),
        "saved_count": saved_count,
    }

def save_uploaded_files_to_dir(files: Iterable[tuple[str, bytes]], target_dir: Path) -> dict[str, str | int]:
    ensure_uploads_dir()
    target_dir = target_dir.resolve()
    uploads_root = UPLOADS_DIR.resolve()
    if not str(target_dir).startswith(str(uploads_root)):
        raise ValueError("Target upload directory is outside the uploads workspace.")
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_count = _write_uploaded_files(files, target_dir)
    return {
        "upload_dir": str(target_dir),
        "saved_count": saved_count,
    }


def _write_uploaded_files(files: Iterable[tuple[str, bytes]], target_dir: Path) -> int:
    saved_count = 0
    for raw_name, content in files:
        relative_path = sanitize_relative_filename(raw_name)
        file_path = target_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        saved_count += 1
    return saved_count
