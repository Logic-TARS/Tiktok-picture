from __future__ import annotations

import threading
from typing import Any

from app import database
from app.config import load_config
from app.deepseek_client import generate_caption
from app.logger import get_logger
from app.publisher.douyin import publish_to_creator

LOGGER = get_logger("app.services.jobs")


def create_gallery_jobs(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    groups = payload.get("groups") or []
    topic = payload.get("topic") or config.get("topic")
    style = payload.get("style") or config.get("caption_style")
    account_position = payload.get("account_position") or config.get("account_position")
    keywords = payload.get("keywords", "")
    banned_words = payload.get("banned_words", "")
    auto_caption = bool(payload.get("auto_caption", True))
    replace_existing = bool(payload.get("replace_existing", True))
    hashtags_count = min(int(config.get("hashtags_count", 5) or 5), 5)
    created: list[dict[str, Any]] = []
    replaced_count = 0

    if replace_existing:
        replaced_count = database.delete_jobs_by_status(
            ["pending", "captioning", "failed"],
            material_type="image_gallery",
        )
        if replaced_count:
            LOGGER.info("Removed %s existing draft jobs before rebuild", replaced_count)

    for index, group in enumerate(groups, start=1):
        paths = group.get("paths") if isinstance(group, dict) else group
        if not paths:
            continue
        caption = {"title": "", "body": "", "hashtags": []}
        status = "pending"
        if auto_caption:
            status = "captioning"
            LOGGER.info("Generating caption for group %s with %s images", index, len(paths))
            caption = generate_caption(
                config,
                {
                    "topic": topic,
                    "style": style,
                    "account_position": account_position,
                    "keywords": keywords,
                    "banned_words": banned_words,
                    "hashtags_count": hashtags_count,
                    "group_index": index,
                    "material_count": len(paths),
                },
            )
            status = "pending"

        job = database.create_job(
            paths,
            title=caption.get("title", ""),
            body=caption.get("body", ""),
            hashtags=caption.get("hashtags", []),
            material_type="image_gallery",
            publish_mode="semi_auto",
            status=status,
        )
        created.append(job)
        LOGGER.info("Created job %s with %s images", job["id"], len(paths))
    return {"jobs": created, "replaced_count": replaced_count}


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
