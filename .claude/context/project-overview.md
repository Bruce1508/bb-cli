# Project Overview

## What this project is

`bb-cli` is a terminal-first Blackboard client for students. It helps students manage deadlines, grades, announcements, course content, and downloaded files without relying on the Blackboard web UI for everyday workflows.

## What is implemented now

The current repository already covers the Day 1–9 foundation:

- CLI commands and user-facing flows in `bb/cli.py`
- local SQLite persistence and migrations in `bb/db.py`
- iCal import and Blackboard sync in `bb/sync.py`
- Blackboard auth and scraping in `bb/adapters/blackboard_ultra.py`
- course-content browsing, caching, downloads, and file-opening flows across `bb/cli.py` and `bb/models/content.py`
- AI-facing query helpers in `bb/tools/queries.py`

## What the next delivery milestone is

The immediate milestone is Day 10: `bb chat`.

That means Claude should reason about the current repo as a strong terminal/data/sync foundation that is about to gain a chat runtime built on top of the existing tool layer rather than bypassing it.

## Product assumptions

- The product is terminal-first, not browser-first.
- Local data and cached files are a core strength.
- Blackboard facts should come from local state, sync results, or tool outputs.
- The current repository state is more authoritative than older notes or idealized architecture sketches.

## Paths to know first

- `pyproject.toml`
- `bb/cli.py`
- `bb/db.py`
- `bb/sync.py`
- `bb/adapters/blackboard_ultra.py`
- `bb/tools/queries.py`
- `bb/models/content.py`
- `selectors/blackboard_ultra.toml`
