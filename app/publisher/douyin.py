from __future__ import annotations

from typing import Any

from app.logger import get_logger
from app.media.image_9x16 import cleanup_temp_dir, prepare_9x16_uploads


ACTIVE_SESSIONS: list[tuple[Any, Any]] = []
LOGGER = get_logger("app.publisher.douyin")


def friendly_publish_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower_message = message.lower()
    if "non-multiple file input can only accept single file" in lower_message:
        return "当前命中的是单文件上传控件，不是图集上传入口。请确认页面已切到“发布图文”。"
    if "no candidate selector matched" in lower_message or "no node found for selector" in lower_message:
        return "页面控件没有匹配到，抖音创作者中心页面结构可能变了。请查看日志。"
    if "timeout" in lower_message or "timed out" in lower_message:
        return "等待抖音创作者中心页面超时。请确认当前账号仍处于登录状态。"
    if "net::err" in lower_message:
        return "抖音创作者中心页面打开失败。请检查网络和浏览器环境。"
    return message or "发布失败，请查看日志。"


def publish_to_creator(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium"
        ) from exc

    upload_url = config.get("creator_upload_url") or "https://creator.douyin.com/creator-micro/content/upload"
    profile_dir = config.get("browser_profile_dir") or "data/browser-profile"
    browser_path = config.get("browser_path") or None
    upload_selector = config.get("upload_selector") or "input[type='file']"

    playwright = sync_playwright().start()
    launch_options: dict[str, Any] = {"headless": False}
    if browser_path:
        launch_options["executable_path"] = browser_path

    temp_upload_dir = None
    context = None

    try:
        context = playwright.chromium.launch_persistent_context(profile_dir, **launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(upload_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        LOGGER.info("Opened creator upload page for job %s", job["id"])

        ensure_publish_mode(page, job)
        upload_input = resolve_upload_input(page, job, upload_selector)
        upload_paths = job["material_paths"]
        if should_force_9x16(job, config):
            upload_mode = str(config.get("force_9x16_mode") or "blur_background")
            upload_paths, temp_upload_dir = prepare_9x16_uploads(job["material_paths"], mode=upload_mode)
            LOGGER.info(
                "Prepared %s temporary 9:16 images for job %s with mode %s",
                len(upload_paths),
                job["id"],
                upload_mode,
            )

        upload_input.set_input_files(upload_paths, timeout=60000)
        page.wait_for_timeout(2500)
        LOGGER.info("Uploaded %s files for job %s", len(upload_paths), job["id"])

        title_text = normalize_publish_title(job.get("title", ""))
        description_text = build_publish_description(job)
        fill_result = fill_caption(page, title_text, description_text, config)
        LOGGER.info("Fill result for job %s: %s", job["id"], fill_result)

        music_status = select_suggested_music(page)
        LOGGER.info("Music selection result for job %s: %s", job["id"], music_status)

        click_publish(page)
        LOGGER.info("Clicked publish button for job %s", job["id"])

        if temp_upload_dir:
            cleanup_temp_dir(temp_upload_dir)
            LOGGER.info("Cleaned temporary 9:16 files for job %s", job["id"])
            temp_upload_dir = None

        ACTIVE_SESSIONS.append((playwright, context))
        return {
            "status": "submitted",
            "message": f"已自动发布。音乐：{music_status}",
            "fill_result": fill_result,
            "music_status": music_status,
        }
    except PlaywrightTimeoutError as exc:
        LOGGER.exception("Creator page timed out for job %s", job["id"])
        if context:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
        cleanup_temp_dir(temp_upload_dir)
        raise RuntimeError(friendly_publish_error(exc)) from exc
    except Exception as exc:
        LOGGER.exception("Publisher failed for job %s", job["id"])
        if context:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
        cleanup_temp_dir(temp_upload_dir)
        raise RuntimeError(friendly_publish_error(exc)) from exc


def should_force_9x16(job: dict[str, Any], config: dict[str, Any]) -> bool:
    return bool(config.get("force_9x16_upload")) and job.get("material_type") == "image_gallery"


def normalize_publish_title(title: str) -> str:
    compact = "".join(str(title or "").split())
    return compact[:20]


def build_publish_description(job: dict[str, Any]) -> str:
    hashtags = []
    for tag in job.get("hashtags", [])[:5]:
        text = str(tag).strip()
        if not text:
            continue
        hashtags.append(text if text.startswith("#") else f"#{text}")
    parts = [str(job.get("body", "")).strip(), " ".join(hashtags).strip()]
    return "\n\n".join(part for part in parts if part)


def ensure_publish_mode(page: Any, job: dict[str, Any]) -> None:
    if job.get("material_type") != "image_gallery":
        return

    tabs = page.locator("div[class*='tab-item']")
    for _ in range(10):
        if tabs.count() >= 2:
            break
        page.wait_for_timeout(800)

    if tabs.count() >= 2:
        try:
            current_text = tabs.nth(0).inner_text(timeout=1500)
            target_text = tabs.nth(1).inner_text(timeout=1500)
            LOGGER.info("Switching publish tab for job %s: %s -> %s", job["id"], current_text, target_text)
        except Exception:
            pass
        tabs.nth(1).click(timeout=5000)
        page.wait_for_timeout(1500)
        return

    if click_text(page, ["发布图文", "图文"], exact=False):
        page.wait_for_timeout(1500)
        return

    LOGGER.warning("Publish tabs not found for job %s", job["id"])


def resolve_upload_input(page: Any, job: dict[str, Any], upload_selector: str) -> Any:
    custom_selector = (upload_selector or "").strip()
    if custom_selector and custom_selector != "input[type='file']":
        locator = page.locator(custom_selector).first
        if locator.count():
            LOGGER.info("Using custom upload selector for job %s: %s", job["id"], custom_selector)
            return locator

    if job.get("material_type") == "image_gallery":
        candidates = [
            "input[type='file'][multiple][accept*='image']",
            "input[type='file'][accept*='image'][multiple]",
            "input[type='file'][accept*='image/png']",
            "input[type='file'][accept*='image/jpeg']",
        ]
        for selector in candidates:
            locator = page.locator(selector).first
            if locator.count():
                LOGGER.info("Using gallery upload selector for job %s: %s", job["id"], selector)
                return locator
        raise RuntimeError("未找到图集上传控件，请确认当前页面已切到“发布图文”。")

    return page.locator(custom_selector or "input[type='file']").first


def fill_caption(page: Any, title: str, description: str, config: dict[str, Any]) -> dict[str, Any]:
    result = {"title": "not_configured", "caption": "not_filled"}

    title_selector = config.get("title_selector") or ""
    if title_selector:
        try:
            page.locator(title_selector).first.fill(title, timeout=5000)
            result["title"] = "filled_by_config_selector"
        except Exception as exc:
            result["title"] = f"failed_by_config_selector: {exc}"
    else:
        result["title"] = fill_by_candidates(
            page,
            title,
            [
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "[contenteditable='true'][placeholder*='标题']",
            ],
        )

    caption_selector = config.get("caption_selector") or ""
    if caption_selector:
        try:
            page.locator(caption_selector).first.fill(description, timeout=5000)
            result["caption"] = "filled_by_config_selector"
            return result
        except Exception as exc:
            result["caption"] = f"failed_by_config_selector: {exc}"

    result["caption"] = fill_by_candidates(
        page,
        description,
        [
            "textarea[placeholder*='添加作品简介']",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='文案']",
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


def select_suggested_music(page: Any) -> str:
    click_text(page, ["添加合适作品风格音乐", "添加音乐", "选择音乐"], exact=False)
    page.wait_for_timeout(1200)
    script = """
    () => {
      const isVisible = (node) => {
        if (!node) return false;
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const clickableAncestor = (node) => node.closest("button,[role='button'],div,li");
      const nodes = Array.from(document.querySelectorAll("div, span, button"));
      for (const node of nodes) {
        const text = (node.innerText || node.textContent || "").trim();
        if (!text || !isVisible(node)) continue;
        if (text.includes("热度")) {
          const target = clickableAncestor(node);
          if (target && isVisible(target)) {
            target.click();
            return true;
          }
        }
      }
      return false;
    }
    """
    try:
        if page.evaluate(script):
            page.wait_for_timeout(1000)
            return "已自动选择推荐音乐"
    except Exception:
        pass
    return "未命中推荐音乐，已跳过"


def click_publish(page: Any) -> None:
    if click_button_by_text(page, ["发布", "立即发布"]):
        page.wait_for_timeout(1500)
        click_button_by_text(page, ["确认发布", "继续发布"])
        page.wait_for_timeout(1500)
        return
    raise RuntimeError("未找到发布按钮。")


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


def click_button_by_text(page: Any, texts: list[str]) -> bool:
    for text in texts:
        try:
            buttons = page.locator("button").filter(has_text=text)
            count = buttons.count()
            for index in range(count - 1, -1, -1):
                button = buttons.nth(index)
                if button.is_visible(timeout=800):
                    button.click(timeout=3000)
                    return True
        except Exception:
            continue
    return click_text(page, texts, exact=True)
