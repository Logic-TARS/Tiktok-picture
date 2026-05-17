from __future__ import annotations

from typing import Any

from app.logger import get_logger
from app.media.image_9x16 import PLATFORM_RESOLUTIONS, cleanup_temp_dir, prepare_platform_uploads


ACTIVE_SESSIONS: list[tuple[Any, Any]] = []
LOGGER = get_logger("app.publisher.xiaohongshu")


def friendly_publish_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower_message = message.lower()
    if "non-multiple file input can only accept single file" in lower_message:
        return "当前命中的是单文件上传控件，不是图集上传入口。请确认小红书发布页面。"
    if "image gallery upload input" in lower_message:
        return "未找到图集上传控件，请确认小红书发布页面已加载。"
    if "no candidate selector matched" in lower_message or "no node found for selector" in lower_message:
        return "页面控件没有匹配到，小红书创作者页面结构可能变了。请查看日志。"
    if "timeout" in lower_message or "timed out" in lower_message:
        return "等待小红书创作者中心页面超时。请确认当前账号仍处于登录状态。"
    if "net::err" in lower_message:
        return "小红书创作者中心页面打开失败。请检查网络和浏览器环境。"
    return message or "发布失败，请查看日志。"


def publish_to_creator(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium"
        ) from exc

    upload_url = config.get("xiaohongshu_upload_url") or "https://creator.xiaohongshu.com/publish/publish"
    profile_dir = config.get("browser_profile_dir") or "data/browser-profile"
    browser_path = config.get("browser_path") or None
    upload_selector = config.get("xiaohongshu_upload_selector") or config.get("upload_selector") or "input[type='file']"

    playwright = sync_playwright().start()
    launch_options: dict[str, Any] = {"headless": False}
    if browser_path:
        launch_options["executable_path"] = browser_path

    context = None
    temp_upload_dir = None

    try:
        context = playwright.chromium.launch_persistent_context(profile_dir, **launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(upload_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        LOGGER.info("Opened Xiaohongshu creator publish page for job %s", job["id"])

        upload_input = resolve_upload_input(page, job, upload_selector)

        upload_paths = list(job["material_paths"])
        if should_force_9x16(job, config):
            upload_mode = str(config.get("force_9x16_mode") or "blur_background")
            target_size = PLATFORM_RESOLUTIONS.get("xiaohongshu", (720, 960))
            upload_paths, temp_upload_dir = prepare_platform_uploads(
                upload_paths, mode=upload_mode, target_size=target_size,
            )
            LOGGER.info(
                "Prepared %s temporary images for Xiaohongshu job %s with mode %s",
                len(upload_paths), job["id"], upload_mode,
            )

        upload_input.set_input_files(upload_paths, timeout=60000)
        page.wait_for_timeout(3000)
        LOGGER.info("Uploaded %s file(s) for Xiaohongshu job %s", len(upload_paths), job["id"])

        title_text = normalize_publish_title(job.get("title", ""))
        description_text = build_publish_description(job)
        fill_result = fill_caption(page, title_text, description_text, config)
        LOGGER.info("Fill result for Xiaohongshu job %s: %s", job["id"], fill_result)

        if temp_upload_dir:
            cleanup_temp_dir(temp_upload_dir)
            LOGGER.info("Cleaned temporary files for Xiaohongshu job %s", job["id"])
            temp_upload_dir = None

        ACTIVE_SESSIONS.append((playwright, context))
        return {
            "status": "need_manual",
            "message": f"素材和文案已填入小红书创作者中心，请手动检查后点击发布。类型：{job.get('material_type')}。",
            "fill_result": fill_result,
        }
    except PlaywrightTimeoutError as exc:
        LOGGER.exception("Xiaohongshu creator page timed out for job %s", job["id"])
        _close_context(playwright, context)
        cleanup_temp_dir(temp_upload_dir)
        raise RuntimeError(friendly_publish_error(exc)) from exc
    except Exception as exc:
        LOGGER.exception("Xiaohongshu publisher failed for job %s", job["id"])
        _close_context(playwright, context)
        cleanup_temp_dir(temp_upload_dir)
        raise RuntimeError(friendly_publish_error(exc)) from exc


def _close_context(playwright: Any, context: Any) -> None:
    if context:
        try:
            context.close()
        except Exception:
            pass
    try:
        playwright.stop()
    except Exception:
        pass


def should_force_9x16(job: dict[str, Any], config: dict[str, Any]) -> bool:
    return bool(config.get("force_9x16_upload")) and job.get("material_type") == "image_gallery"


def normalize_publish_title(title: str) -> str:
    compact = "".join(str(title or "").split())
    return compact[:20]


def build_publish_description(job: dict[str, Any]) -> str:
    hashtags = []
    for tag in job.get("hashtags", [])[:10]:
        text = str(tag).strip()
        if not text:
            continue
        hashtags.append(text if text.startswith("#") else f"#{text}")
    parts = [str(job.get("body", "")).strip(), " ".join(hashtags).strip()]
    return "\n\n".join(part for part in parts if part)


def resolve_upload_input(page: Any, job: dict[str, Any], upload_selector: str) -> Any:
    custom_selector = (upload_selector or "").strip()
    if custom_selector and custom_selector != "input[type='file']":
        locator = page.locator(custom_selector).first
        if locator.count():
            LOGGER.info("Using custom upload selector for Xiaohongshu job %s: %s", job["id"], custom_selector)
            return locator

    candidates = [
        "input[type='file'][multiple]",
        "input[type='file'][accept*='image']",
        "input[type='file']",
    ]
    for selector in candidates:
        locator = page.locator(selector).first
        if locator.count():
            LOGGER.info("Using upload selector for Xiaohongshu job %s: %s", job["id"], selector)
            return locator
    raise RuntimeError("Upload input not found.")


def fill_caption(page: Any, title: str, description: str, config: dict[str, Any]) -> dict[str, Any]:
    result = {"title": "not_configured", "caption": "not_filled"}

    title_selector = config.get("xiaohongshu_title_selector") or config.get("title_selector") or ""
    if title_selector:
        try:
            page.locator(title_selector).first.fill(title, timeout=5000)
            result["title"] = "filled_by_config_selector"
        except Exception as exc:
            result["title"] = f"failed_by_config_selector: {exc}"
    else:
        result["title"] = fill_by_candidates(
            page, title,
            [
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "[contenteditable='true'][placeholder*='标题']",
                "input[placeholder*='填写标题']",
            ],
        )

    caption_selector = config.get("xiaohongshu_caption_selector") or config.get("caption_selector") or ""
    if caption_selector:
        try:
            page.locator(caption_selector).first.fill(description, timeout=5000)
            result["caption"] = "filled_by_config_selector"
            return result
        except Exception as exc:
            result["caption"] = f"failed_by_config_selector: {exc}"

    result["caption"] = fill_by_candidates(
        page, description,
        [
            "textarea[placeholder*='正文']",
            "textarea[placeholder*='写']",
            "div[contenteditable='true']",
            "textarea",
            "[contenteditable='true']",
        ],
    )
    if result["caption"].startswith("failed"):
        result["caption"] = fill_first_editable_with_js(page, description)
    return result


def fill_by_candidates(page: Any, value: str, selectors: list[str]) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.fill(value, timeout=4000)
            return f"filled: {selector}"
        except Exception:
            continue
    return "failed: no candidate selector matched"


def fill_first_editable_with_js(page: Any, value: str) -> str:
    script = """
    (value) => {
      const nodes = Array.from(document.querySelectorAll("textarea, [contenteditable='true']"));
      const node = nodes.find((item) => item.offsetParent !== null) || nodes[0];
      if (!node) return false;
      if (node.tagName.toLowerCase() === "textarea") {
        node.value = value;
      } else {
        node.innerText = value;
      }
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    """
    try:
        ok = page.evaluate(script, value)
        return "filled_by_js" if ok else "failed: no editable element found"
    except Exception as exc:
        return f"failed_by_js: {exc}"


def click_text(page: Any, texts: list[str], *, exact: bool = False) -> bool:
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=exact)
            count = locator.count()
            for index in range(count):
                node = locator.nth(index)
                if node.is_visible(timeout=800):
                    node.click(timeout=3000)
                    return True
        except Exception:
            continue
    return False
