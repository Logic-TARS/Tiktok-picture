from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from app import database
from app.config import DATA_DIR, load_config
from app.deepseek_client import generate_caption
from app.logger import get_logger
from app.media.video_mixer import mix_images_to_video, normalize_effect_mode
from app.publisher.douyin import publish_to_creator

LOGGER = get_logger("app.services.jobs")


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

    created: list[dict[str, Any]] = []
    replaced_count = 0

    if replace_existing:
        replaced_count = database.delete_jobs_by_status(["pending", "captioning", "failed"])
        if replaced_count:
            LOGGER.info("Removed %s existing draft jobs before rebuild", replaced_count)

    if publish_type == "video":
        video_items = payload.get("video_items") or []
        groups = payload.get("groups") or []
        if video_source == "mix_from_images":
            created = _create_mixed_video_jobs(
                groups=groups,
                config=config,
                topic=topic,
                style=style,
                account_position=account_position,
                keywords=keywords,
                banned_words=banned_words,
                hashtags_count=hashtags_count,
                auto_caption=auto_caption,
                effect_mode=mixed_video_effect,
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
    effect_mode: str,
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
    outputs_dir = DATA_DIR / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    for index, group in enumerate(groups, start=1):
        paths = group.get("paths") if isinstance(group, dict) else group
        if not paths:
            continue
        output_name = f"mixed_{index:03d}_{uuid.uuid4().hex[:8]}.mp4"
        mixed_video_path = mix_images_to_video(
            paths,
            output_name=output_name,
            effect_mode=effect_mode,
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
            "Created mixed video job %s from %s images with effect %s",
            job["id"],
            len(paths),
            effect_mode,
        )
    return created


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
