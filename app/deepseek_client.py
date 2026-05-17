from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.logger import get_logger

LOGGER = get_logger("app.deepseek")


PLATFORM_CONFIGS: dict[str, dict[str, Any]] = {
    "douyin": {
        "system": "你是抖音二次元图集账号的中文文案助手。只输出 JSON。",
        "title_max": 20,
        "hashtags_max": 5,
        "constraints": (
            "要求：\n"
            "1. 标题最多 20 个字符，尽量 6-12 个中文字符，更抽象、更氛围化。\n"
            "2. 标题不要写'第几弹''几张''壁纸''头像''图集''收藏''适合做头像'等直白词，也不要带数字。\n"
            "3. 正文适合抖音图集，保留二次元氛围，避免低俗擦边。\n"
            "4. 话题最多 5 个，适合二次元、壁纸、头像、图文内容。\n"
            "5. 只输出 JSON，不要 Markdown。\n"
        ),
    },
    "kuaishou": {
        "system": "你是快手二次元图集账号的中文文案助手。只输出 JSON。",
        "title_max": 25,
        "hashtags_max": 5,
        "constraints": (
            "要求：\n"
            "1. 标题最多 25 个字符，吸引点击。\n"
            "2. 正文不超过 1000 字，适合快手用户阅读习惯，保留二次元氛围。\n"
            "3. 话题最多 5 个，适合快手二次元内容。\n"
            "4. 只输出 JSON，不要 Markdown。\n"
        ),
    },
    "xiaohongshu": {
        "system": "你是小红书二次元图集账号的中文文案助手。只输出 JSON。",
        "title_max": 20,
        "hashtags_max": 10,
        "constraints": (
            "要求：\n"
            "1. 标题最多 20 个字符，吸引人点击。\n"
            "2. 正文可以稍长，适合小红书排版风格，保留二次元氛围，段落分明。\n"
            "3. 话题最多 10 个，覆盖二次元、动漫、审美相关标签。\n"
            "4. 只输出 JSON，不要 Markdown。\n"
        ),
    },
}


def generate_caption(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    api_key = config.get("deepseek_api_key", "")
    if not api_key:
        LOGGER.info("DeepSeek API key not configured, using local template")
        return local_caption(payload)

    base_url = str(config.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = config.get("deepseek_model") or "deepseek-v4-flash"
    platform = payload.get("platform") or config.get("platform") or "douyin"
    platform_config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["douyin"])
    if base_url.endswith("/anthropic"):
        raise RuntimeError(
            "Current project uses the OpenAI-compatible DeepSeek endpoint. "
            "Use https://api.deepseek.com instead of https://api.deepseek.com/anthropic."
        )
    endpoint = f"{base_url}/chat/completions"
    prompt = build_prompt(payload, platform=platform)
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": platform_config["system"],
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        LOGGER.error("DeepSeek HTTP error %s: %s", exc.code, detail)
        raise RuntimeError(f"DeepSeek request failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        LOGGER.error("DeepSeek URL error: %s", exc.reason)
        raise RuntimeError(f"DeepSeek request failed: {exc.reason}") from exc

    content = data["choices"][0]["message"]["content"]
    result = normalize_caption_result(parse_caption_json(content), payload, platform=platform)
    result["source"] = "deepseek"
    LOGGER.info("DeepSeek caption generated with model %s", model)
    return result


def build_prompt(payload: dict[str, Any], platform: str = "douyin") -> str:
    topic = payload.get("topic", "二次元图集")
    style = payload.get("style", "治愈收藏向")
    account_position = payload.get("account_position", "二次元图片号")
    keywords = payload.get("keywords", "")
    banned_words = payload.get("banned_words", "")
    platform_config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["douyin"])
    hashtags_count = min(int(payload.get("hashtags_count") or platform_config["hashtags_max"]), platform_config["hashtags_max"])
    group_index = payload.get("group_index", 1)
    material_count = payload.get("material_count", 4)

    platform_name_map = {
        "douyin": "抖音",
        "kuaishou": "快手",
        "xiaohongshu": "小红书",
    }
    platform_label = platform_name_map.get(platform, "抖音")

    return f"""
请为{platform_label}创作者服务平台的多图图集生成发布文案。
账号定位：{account_position}
内容主题：{topic}
素材类型：二次元多图图集
本组序号：第 {group_index} 组
本组图片数量：{material_count} 张
文案风格：{style}
关键词：{keywords}
禁用词：{banned_words}
话题数量：{hashtags_count}

{platform_config["constraints"]}
JSON 格式：
{{
  "title": "标题",
  "body": "正文",
  "hashtags": ["话题1", "话题2"],
  "comment_prompt": "评论引导"
}}
""".strip()


def parse_caption_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "title": fallback_abstract_title({}),
            "body": content.strip(),
            "hashtags": ["二次元", "动漫", "壁纸", "头像", "图文"],
            "comment_prompt": "你最喜欢哪一张？",
        }
    hashtags = data.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = [item.strip("# ") for item in re.split(r"[\s,，]+", hashtags) if item]
    return {
        "title": str(data.get("title", fallback_abstract_title({}))).strip(),
        "body": str(data.get("body", "")).strip(),
        "hashtags": [str(tag).strip("# ") for tag in hashtags if str(tag).strip("# ")],
        "comment_prompt": str(data.get("comment_prompt", "")).strip(),
        "raw": content,
    }


def local_caption(payload: dict[str, Any]) -> dict[str, Any]:
    platform = payload.get("platform") or "douyin"
    platform_config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["douyin"])
    style = payload.get("style") or "治愈收藏向"
    style_line = {
        "治愈收藏向": "把今天的温柔留在这组图里，适合慢慢看，也适合先存下来。",
        "情绪共鸣向": "有些画面不需要解释，看见的一瞬间就已经懂了。",
        "头像壁纸向": "这一组更偏干净、耐看和有氛围感，适合反复换着看。",
        "反差钩子向": "第一眼很安静，越看越有后劲。",
        "人设故事向": "像是某个角色路过时留下的一小段心事。",
        "评论互动向": "如果只能留下一张，你会选哪一张？",
    }.get(style, "这一组适合先存起来，之后慢慢翻。")
    result = {
        "title": fallback_abstract_title(payload),
        "body": f"{style_line}\n喜欢这种氛围的话，可以先收藏，之后慢慢换。",
        "hashtags": ["二次元", "动漫", "壁纸", "头像", "图文"],
        "comment_prompt": "你最喜欢哪一张？",
        "raw": "",
        "source": "local_template",
    }
    return normalize_caption_result(result, payload, platform=platform)


def normalize_caption_result(result: dict[str, Any], payload: dict[str, Any], platform: str = "douyin") -> dict[str, Any]:
    platform_config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["douyin"])
    normalized = dict(result)
    normalized["title"] = normalize_title(str(result.get("title", "")).strip(), payload, title_max=platform_config["title_max"])
    normalized["body"] = str(result.get("body", "")).strip()
    normalized["hashtags"] = normalize_hashtags(result.get("hashtags") or [], limit=platform_config["hashtags_max"])
    return normalized


def normalize_title(title: str, payload: dict[str, Any], title_max: int = 20) -> str:
    cleaned = re.sub(r"\s+", "", title)
    cleaned = cleaned[:title_max]
    if not cleaned:
        return fallback_abstract_title(payload)

    banned_parts = [
        "第", "弹", "几张", "壁纸", "头像", "图集", "收藏", "适合", "手机", "美图", "分享",
    ]
    if any(part in cleaned for part in banned_parts) or re.search(r"\d", cleaned):
        return fallback_abstract_title(payload)
    return cleaned


def normalize_hashtags(hashtags: list[Any], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in hashtags:
        text = str(tag).strip().strip("#")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def fallback_abstract_title(payload: dict[str, Any]) -> str:
    keywords_text = " ".join(
        str(payload.get(key, "")).strip() for key in ["keywords", "topic", "style"] if payload.get(key)
    )
    mood_pairs = [
        ("雨", "雨幕"),
        ("夜", "夜色"),
        ("蓝", "雾蓝"),
        ("霓虹", "霓虹"),
        ("风", "风信"),
        ("雪", "雪痕"),
        ("光", "微光"),
        ("海", "海雾"),
        ("星", "星屿"),
        ("少女", "少女"),
        ("银发", "银月"),
        ("孤独", "孤岛"),
        ("治愈", "静愈"),
    ]
    prefix = "静谧"
    for key, value in mood_pairs:
        if key in keywords_text:
            prefix = value
            break

    suffix_pairs = [
        ("情绪", "低语"),
        ("故事", "来信"),
        ("头像", "侧影"),
        ("壁纸", "光景"),
        ("收藏", "心事"),
        ("治愈", "微梦"),
    ]
    suffix = "心事"
    for key, value in suffix_pairs:
        if key in keywords_text:
            suffix = value
            break

    return f"{prefix}{suffix}"[:20]
