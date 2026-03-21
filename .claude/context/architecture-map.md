# Architecture Map

This repository is easiest to understand as four connected lanes.

## 1. CLI surface

Primary path:
- `bb/cli.py`

This is the terminal-facing orchestration layer. It exposes commands for setup, sync, due dates, grades, announcements, course browsing, downloads, cache clearing, and opening items.

When a request changes command behavior, output format, command options, or command sequencing, start here.

## 2. Data persistence and sync

Primary paths:
- `bb/db.py`
- `bb/sync.py`

`bb/db.py` owns schema, migrations, upserts, sync logs, notification cooldowns, course mapping, and download records.

`bb/sync.py` owns iCal retry logic, activity-stream sync, grade sync, and HTML snapshot saves when stream scraping yields zero items.

When a request changes how Blackboard data is fetched, stored, or reconciled, this lane is involved.

## 3. Blackboard scraping and content acquisition

Primary paths:
- `bb/adapters/blackboard_ultra.py`
- `selectors/blackboard_ultra.toml`
- `bb/models/content.py`

`bb/adapters/blackboard_ultra.py` owns Blackboard auth, session restore, activity-stream scraping, grades scraping, course discovery, and course-content scraping.

`selectors/blackboard_ultra.toml` is the runtime selector source and should be treated as part of the scraping system, not as a peripheral file.

`bb/models/content.py` defines the content tree shape that downstream commands and tools depend on.

When Blackboard UI changes, selector drift, auth/session issues, or content-tree problems appear, inspect this lane first.

## 4. AI-facing query layer and future chat integration

Primary paths:
- `bb/tools/queries.py`
- `bb/db.py`
- `bb/models/content.py`

`bb/tools/queries.py` is the current AI-facing surface. It exposes deadline, grades, announcements, sync status, course content, content search, downloaded-file listing, and PDF reading.

This lane matters now even before the full chat runtime lands, because Day 10 `bb chat` should build on top of these tool shapes instead of bypassing them.

## How the lanes connect

Typical flow today:

1. user runs a command in `bb/cli.py`
2. data is fetched or updated through `bb/sync.py` and `bb/adapters/blackboard_ultra.py`
3. data is stored or queried through `bb/db.py`
4. content trees are shaped through `bb/models/content.py`
5. AI-facing access happens through `bb/tools/queries.py`

## Practical guidance

- If the issue is user-visible command behavior, start at `bb/cli.py`.
- If the issue is wrong or missing stored data, inspect `bb/db.py` and `bb/sync.py`.
- If the issue is Blackboard DOM or scraping behavior, inspect `bb/adapters/blackboard_ultra.py` and `selectors/blackboard_ultra.toml` together.
- If the issue is future chat/tool behavior, inspect `bb/tools/queries.py` before inventing prompt-only fixes.
