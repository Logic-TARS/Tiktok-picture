# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-platform (抖音/快手/小红书) semi-automated publishing tool for anime/2D image galleries. Local web app: scan images → DeepSeek generates per-platform captions → Playwright opens the creator page with pre-filled form (user manually clicks publish).

## Commands

```powershell
# Start server (conda env)
conda activate douyin-publisher
python -m app.main
# Opens at http://127.0.0.1:8765

# Or use the startup script
.\start.ps1

# Install from scratch
conda env create -f environment.yml
conda activate douyin-publisher
python -m playwright install chromium
```

## Architecture

```
app/
├── main.py              # HTTP server on :8765 (ThreadingHTTPServer, no framework)
├── config.py            # Config: defaults → data/config.json → .env / env.txt → env vars
├── database.py          # SQLite (jobs, publish_records, settings tables)
├── logger.py            # Rotating file + console logger
├── deepseek_client.py   # DeepSeek caption generation with per-platform prompts
├── media/
│   ├── scanner.py       # Recursive directory scan for images/videos/audio
│   ├── uploads.py       # File upload → data/uploads/{id}/
│   ├── image_9x16.py    # PIL-based resize with platform-specific target sizes
│   └── video_mixer.py   # FFmpeg image slideshow → video with effects
├── services/
│   └── jobs.py          # Job creation & async publish orchestration (platform dispatch)
├── publisher/
│   ├── douyin.py        # Playwright automation for 抖音
│   ├── kuaishou.py      # Playwright automation for 快手
│   └── xiaohongshu.py   # Playwright automation for 小红书
└── static/              # Web UI (Chinese): index.html, app.js, styles.css
```

### Key Design Decisions

- **Semi-automated only**: Browser automation fills forms but does NOT click final publish
- **No web framework**: Uses stdlib `http.server` (ThreadingHTTPServer)
- **No DeepSeek SDK**: Uses raw `urllib.request` for API calls
- **No test files**: Project has no test suite
- **Config cascade**: defaults → `data/config.json` → `.env` / `env.txt` → process environment overrides
- **Job status flow**: `pending` → `captioning` → `publishing` → `need_manual` → `submitted` / `published` / `failed`
- **Captions per platform**: DeepSeek prompts differ by platform (title length, hashtags count, tone)
- **Image sizes per platform**: douyin=9:16, kuaishou=9:16, xiaohongshu=3:4

### Database (SQLite, `data/app.db`)

- **jobs**: id, material_type, material_paths (JSON), title, body, hashtags (JSON), **platform** (douyin/kuaishou/xiaohongshu), status, error_message, douyin_url, timestamps
- **publish_records**: Audit log of publish attempts
- **settings**: Key-value store

### Platform Support

| Platform  | URL resolution          | Title max | Hashtags max | Image ratio |
|-----------|------------------------|-----------|-------------|-------------|
| douyin    | 1080×1920 (9:16)       | 20 chars  | 5           | 9:16        |
| kuaishou  | 1080×1920 (9:16)       | 25 chars  | 5           | 9:16        |
| xiaohongshu | 720×960 (3:4)        | 20 chars  | 10          | 3:4         |

Publishers share the same function signature: `publish_to_creator(job, config) -> dict`.
Dispatch is via `PUBLISHERS` dict in `services/jobs.py`.

### Dependencies

- `playwright>=1.44.0` — browser automation
- `Pillow>=10.3.0` — image processing
- FFmpeg — video mixing (optional)

### File Paths

- Uploads: `data/uploads/{id}/`
- Video outputs: `data/outputs/`
- Browser profile: `data/browser-profile/`
- Logs: `data/logs/app.log`, `data/logs/error.log`
- Config: `data/config.json`
- Database: `data/app.db`
