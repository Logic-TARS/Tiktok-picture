from __future__ import annotations

from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def scan_paths(raw_paths: list[str], group_size: int = 4) -> dict[str, Any]:
    files: list[Path] = []
    skipped: list[dict[str, str]] = []

    for raw_path in raw_paths:
        raw_path = raw_path.strip().strip('"')
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.exists():
            skipped.append({"path": raw_path, "reason": "path_not_found"})
            continue
        if path.is_dir():
            for item in path.rglob("*"):
                if item.is_file():
                    files.append(item)
        elif path.is_file():
            files.append(path)

    images = sorted(
        [str(path.resolve()) for path in files if path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda value: value.lower(),
    )
    videos = sorted(
        [str(path.resolve()) for path in files if path.suffix.lower() in VIDEO_EXTENSIONS],
        key=lambda value: value.lower(),
    )
    unsupported = sorted(
        [
            str(path.resolve())
            for path in files
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
        ],
        key=lambda value: value.lower(),
    )

    image_groups = [
        {
            "material_type": "image_gallery",
            "paths": images[index : index + group_size],
            "is_full_group": len(images[index : index + group_size]) == group_size,
        }
        for index in range(0, len(images), group_size)
    ]
    video_items = [
        {
            "material_type": "video",
            "paths": [path],
            "is_full_group": True,
        }
        for path in videos
    ]

    return {
        "images": images,
        "videos": videos,
        "unsupported": unsupported,
        "groups": image_groups,
        "image_groups": image_groups,
        "video_items": video_items,
        "skipped": skipped,
        "group_size": group_size,
    }
