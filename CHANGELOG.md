# Changelog

All notable changes to this project are recorded here.

## Unreleased

### In Progress

- Add platform selection groundwork for Douyin, Kuaishou, and Xiaohongshu.
- Add platform-specific caption constraints and publisher modules.
- Add platform badges in the job table.
- Add SQLite migrations for existing databases when new columns are introduced, starting with `jobs.platform` and `publish_records.platform`.
- Expose platform-specific upload URLs and selectors in the UI.
- Align hashtag limits across config, UI, job creation, and caption generation so Xiaohongshu can use up to 10 tags while Douyin and Kuaishou stay at 5.
- Disable Xiaohongshu video task creation until a dedicated video publishing branch is implemented.
- Validate platform values at job creation and publishing.

### Next Changes

- Add platform names to publish records and any future record export output.
- Consider separate browser profile directories per platform to avoid login-state conflicts between Douyin, Kuaishou, and Xiaohongshu.
- Reduce duplicated Playwright publisher code by extracting shared helpers for launching browsers, resolving upload inputs, filling text fields, and formatting captions.
- Add a smoke test or local verification checklist for creating one task per platform and confirming the stored `platform` value is used during publish.

## 2026-05-17

### Added

- Added mixed-video background music support, including audio upload, audio scanning, start offset, and clip duration.
- Added task confirmation and task deletion controls.
- Added generated mixed-video cleanup when deleting unused draft tasks.
- Added 9:16 processing options that save from the UI.
- Added `CLAUDE.md` with project architecture and maintenance notes.

### Changed

- Updated README to describe the current image, video, mixed-video, audio, and task-control capabilities.

## Earlier

### Added

- Imported the initial local Douyin publishing tool.
- Added image gallery workflow, DeepSeek caption generation, SQLite task storage, local web UI, Playwright-assisted Douyin publishing, and initial mixed-video generation.
