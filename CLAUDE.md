# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Douyin (Chinese TikTok) semi-automated publishing tool for anime/2D image galleries. Local web app: scan images → DeepSeek generates captions → Playwright opens Douyin creator page with pre-filled form (user manually clicks publish).

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
├── config.py            # Config: .env → env.txt → data/config.json → env vars
├── database.py          # SQLite (jobs, publish_records, settings tables)
├── logger.py            # Rotating file + console logger
├── deepseek_client.py   # DeepSeek AI caption generation (urllib, no SDK)
├── media/
│   ├── scanner.py       # Recursive directory scan for images/videos/audio
│   ├── uploads.py       # File upload → data/uploads/{id}/
│   ├── image_9x16.py    # PIL-based resize to 1080×1920 (blur or crop)
│   └── video_mixer.py   # FFmpeg image slideshow → video with effects
├── services/
│   └── jobs.py          # Job creation & async publish orchestration
├── publisher/
│   └── douyin.py        # Playwright browser automation for Douyin upload
└── static/              # Web UI (Chinese): index.html, app.js, styles.css
```

### Key Design Decisions

- **Semi-automated only**: Browser automation fills forms but does NOT click final publish (stops at confirmation page for manual review)
- **No web framework**: Uses stdlib `http.server` (ThreadingHTTPServer), not Flask/FastAPI
- **No DeepSeek SDK**: Uses raw `urllib.request` for API calls
- **No test files**: Project has no test suite
- **Config cascade**: defaults → `data/config.json` → `.env` / `env.txt` injected into environment → process environment overrides (in `app/config.py`)
- **Job status flow**: `pending` → `captioning` → `publishing` → `need_manual` → `submitted` / `published` / `failed`
- **Captions**: DeepSeek generates title (≤20 chars), body, hashtags (≤5), comment_prompt; falls back to local templates if no API key

### Database (SQLite, `data/app.db`)

- **jobs**: id, material_type (`image_gallery`|`video`), material_paths (JSON), title, body, hashtags (JSON), status, error_message, douyin_url, timestamps
- **publish_records**: Audit log of publish attempts
- **settings**: Key-value store

### Dependencies

- `playwright>=1.44.0` — browser automation (only needed for "半自动发布")
- `Pillow>=10.3.0` — image processing
- FFmpeg — video mixing (optional, conda-installed)

### Playwright Publishing Flow

1. Launches Chromium with persistent profile (`data/browser-profile/`)
2. Opens Douyin creator upload page
3. Switches to image or video tab
4. Uploads files via file input selector
5. Fills title/caption via JS or selector
6. Auto-selects suggested music
7. Leaves browser open — user clicks publish manually

### File Paths

- Uploads: `data/uploads/{id}/`
- Video outputs: `data/outputs/`
- Browser profile: `data/browser-profile/`
- Logs: `data/logs/app.log`, `data/logs/error.log`
- Config: `data/config.json`
- Database: `data/app.db`
