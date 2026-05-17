from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from app import database
from app.config import DATA_DIR, load_config
from app.deepseek_client import generate_caption
from app.logger import get_logger
from app.media.image_9x16 import BLUR_BACKGROUND
from app.media.video_mixer import (
    mix_images_to_video,
    normalize_audio_clip_duration,
    normalize_audio_start_seconds,
    normalize_effect_mode,
)
from app.publisher.douyin import publish_to_creator

LOGGER = get_logger("app.services.jobs")
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def create_gallery_jobs(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    topic = payload.get("topic") or config.get("topic")
    style = payload.get("style") or config.get("caption_style")
    account_position = payload.get("account_position") or config.get("account_position")
    keywords = payload.get("keywords", "")
    banned_words = payload.get("banned_words", "")
    auto_caption = bool(payload.get("auto_caption", True))
    replace_existing = bool(payload.get("replace_existing", True))
    hashtags_count = min(int(config.get("hashtags_count", 5) or 5), 5)
    publish_type = str(payload.get("publish_type") or "image_gallery").strip() or "image_gallery"
    video_source = str(payload.get("video_source") or "direct_video").strip() or "direct_video"
    mixed_video_effect = normalize_effect_mode(payload.get("mixed_video_effect") or config.get("mixed_video_effect"))
    mixed_video_frame_mode = str(config.get("force_9x16_mode") or BLUR_BACKGROUND).strip() or BLUR_BACKGROUND

    created: list[dict[str, Any]] = []
    replaced_count = 0

    if replace_existing:
        replaced_count = database.delete_jobs_by_status(["pending", "captioning", "failed"])
        if replaced_count:
            LOGGER.info("Removed %s existing draft jobs before rebuild", replaced_count)

    if publish_type == "video":
        video_items = payload.get("video_items") or []
        groups = payload.get("groups") or []
        selected_audio_path = str(payload.get("selected_audio_path") or "").strip()
        selected_audio_start = normalize_audio_start_seconds(payload.get("selected_audio_start"))
        selected_audio_duration = normalize_audio_clip_duration(payload.get("selected_audio_duration"))
        if video_source == "mix_from_images":
            created = _create_mixed_video_jobs(
                groups=groups,
                selected_audio_path=selected_audio_path,
                selected_audio_start=selected_audio_start,
                selected_audio_duration=selected_audio_duration,
                config=config,
                topic=topic,
                style=style,
                account_position=account_position,
                keywords=keywords,
                banned_words=banned_words,
                hashtags_count=hashtags_count,
                auto_caption=auto_caption,
                effect_mode=mixed_video_effect,
                frame_mode=mixed_video_frame_mode,
            )
        else:
            created = _create_direct_video_jobs(
                video_items=video_items,
                config=config,
                topic=topic,
                style=style,
                account_position=account_position,
                keywords=keywords,
                banned_words=banned_words,
                hashtags_count=hashtags_count,
                auto_caption=auto_caption,
            )
        return {"jobs": created, "replaced_count": replaced_count}

    groups = payload.get("groups") or []
    for index, group in enumerate(groups, start=1):
        paths = group.get("paths") if isinstance(group, dict) else group
        if not paths:
            continue
        caption = _build_caption(
            config=config,
            topic=topic,
            style=style,
            account_position=account_position,
            keywords=keywords,
            banned_words=banned_words,
            hashtags_count=hashtags_count,
            auto_caption=auto_caption,
            group_index=index,
            material_count=len(paths),
        )
        job = database.create_job(
            paths,
            title=caption.get("title", ""),
            body=caption.get("body", ""),
            hashtags=caption.get("hashtags", []),
            material_type="image_gallery",
            publish_mode="semi_auto",
            status="pending",
        )
        created.append(job)
        LOGGER.info("Created image gallery job %s with %s images", job["id"], len(paths))
    return {"jobs": created, "replaced_count": replaced_count}


def _create_direct_video_jobs(
    *,
    video_items: list[dict[str, Any]],
    config: dict[str, Any],
    topic: str,
    style: str,
    account_position: str,
    keywords: str,
    banned_words: str,
    hashtags_count: int,
    auto_caption: bool,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for index, item in enumerate(video_items, start=1):
        paths = item.get("paths") if isinstance(item, dict) else item
        if not paths:
            continue
        caption = _build_caption(
            config=config,
            topic=topic,
            style=style,
            account_position=account_position,
            keywords=keywords,
            banned_words=banned_words,
            hashtags_count=hashtags_count,
            auto_caption=auto_caption,
            group_index=index,
            material_count=len(paths),
        )
        job = database.create_job(
            paths,
            title=caption.get("title", ""),
            body=caption.get("body", ""),
            hashtags=caption.get("hashtags", []),
            material_type="video",
            publish_mode="semi_auto",
            status="pending",
        )
        created.append(job)
        LOGGER.info("Created direct video job %s with %s file(s)", job["id"], len(paths))
    return created


def _create_mixed_video_jobs(
    *,
    groups: list[dict[str, Any]],
    selected_audio_path: str,
    selected_audio_start: float,
    selected_audio_duration: float,
    config: dict[str, Any],
    topic: str,
    style: str,
    account_position: str,
    keywords: str,
    banned_words: str,
    hashtags_count: int,
    auto_caption: bool,
    effect_mode: str,
    frame_mode: str,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    outputs_dir = DATA_DIR / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    bgm_path = _resolve_selected_bgm(selected_audio_path) or _find_bgm_for_groups(groups)

    for index, group in enumerate(groups, start=1):
        paths = group.get("paths") if isinstance(group, dict) else group
        if not paths:
            continue
        output_name = f"mixed_{index:03d}_{uuid.uuid4().hex[:8]}.mp4"
        mixed_video_path = mix_images_to_video(
            paths,
            output_name=output_name,
            effect_mode=effect_mode,
            frame_mode=frame_mode,
            bgm_path=bgm_path or None,
            bgm_start_seconds=selected_audio_start,
            bgm_clip_duration=selected_audio_duration,
        )
        caption = _build_caption(
            config=config,
            topic=topic,
            style=style,
            account_position=account_position,
            keywords=keywords,
            banned_words=banned_words,
            hashtags_count=hashtags_count,
            auto_caption=auto_caption,
            group_index=index,
            material_count=len(paths),
        )
        job = database.create_job(
            [mixed_video_path],
            title=caption.get("title", ""),
            body=caption.get("body", ""),
            hashtags=caption.get("hashtags", []),
            material_type="video",
            cover_path=str(paths[0]) if paths else "",
            publish_mode="semi_auto",
            status="pending",
        )
        created.append(job)
        LOGGER.info(
            "Created mixed video job %s from %s images with effect %s frame_mode %s and bgm %s (start=%s duration=%s)",
            job["id"],
            len(paths),
            effect_mode,
            frame_mode,
            bool(bgm_path),
            selected_audio_start,
            selected_audio_duration,
        )
    return created


def _resolve_selected_bgm(selected_audio_path: str) -> str:
    if not selected_audio_path:
        return ""
    path = Path(selected_audio_path).resolve()
    if path.exists() and path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
        return str(path)
    return ""


def _find_bgm_for_groups(groups: list[dict[str, Any]]) -> str:
    search_roots: list[Path] = []
    for group in groups:
        paths = group.get("paths") if isinstance(group, dict) else group
        if not paths:
            continue
        first_path = Path(str(paths[0])).resolve()
        search_roots.extend([first_path.parent, first_path.parent.parent])

    seen: set[str] = set()
    for root in search_roots:
        root_key = str(root)
        if root_key in seen or not root.exists():
            continue
        seen.add(root_key)
        audio_files = sorted(
            [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS],
            key=lambda item: str(item).lower(),
        )
        if audio_files:
            return str(audio_files[0])
    return ""


def _build_caption(
    *,
    config: dict[str, Any],
    topic: str,
    style: str,
    account_position: str,
    keywords: str,
    banned_words: str,
    hashtags_count: int,
    auto_caption: bool,
    group_index: int,
    material_count: int,
) -> dict[str, Any]:
    if not auto_caption:
        return {"title": "", "body": "", "hashtags": []}

    LOGGER.info("Generating caption for group %s with %s material(s)", group_index, material_count)
    return generate_caption(
        config,
        {
            "topic": topic,
            "style": style,
            "account_position": account_position,
            "keywords": keywords,
            "banned_words": banned_words,
            "hashtags_count": hashtags_count,
            "group_index": group_index,
            "material_count": material_count,
        },
    )


def publish_job_async(job_id: str) -> dict[str, Any]:
    job = database.update_job(job_id, status="publishing", error_message="")
    LOGGER.info("Starting async publish for job %s", job_id)
    thread = threading.Thread(target=_publish_worker, args=(job_id,), daemon=True)
    thread.start()
    return job


def _publish_worker(job_id: str) -> None:
    config = load_config()
    try:
        job = database.get_job(job_id)
        result = publish_to_creator(job, config)
        updated = database.update_job(
            job_id,
            status=result.get("status", "need_manual"),
            error_message=result.get("message", ""),
        )
        database.add_publish_record(updated, updated["status"], updated.get("error_message", ""))
        LOGGER.info("Publish finished for job %s with status %s", job_id, updated["status"])
    except Exception as exc:
        LOGGER.exception("Publish failed for job %s", job_id)
        try:
            job = database.update_job(job_id, status="failed", error_message=str(exc))
            database.add_publish_record(job, "failed", str(exc))
        except Exception:
            pass
