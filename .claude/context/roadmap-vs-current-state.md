# Roadmap vs Current State

This file exists to prevent confusion between implemented repository state and planned future architecture.

## Use these sources in this order

1. Current repository files for implementation truth
2. `PLAN.md` for current delivery priorities
3. Older notes, sketches, or idealized architecture for background only

## Implemented in the current repository

The repository currently shows working foundations for:

- CLI command workflows in `bb/cli.py`
- SQLite persistence and migrations in `bb/db.py`
- iCal and Blackboard sync in `bb/sync.py`
- Blackboard auth and scraping in `bb/adapters/blackboard_ultra.py`
- course-content models in `bb/models/content.py`
- AI-facing query helpers in `bb/tools/queries.py`

## Planned next in the active sprint

The next sprint-facing layers are centered on:

- Day 10 `bb chat`
- Day 11 chat polish and AI-facing improvements
- Day 12 MCP-facing work, tests, and docs
- Day 13–14 packaging and release

## How to reason when sources disagree

- If a brief describes a component but the codebase does not yet show it, treat that component as planned rather than implemented.
- If the current repository shape differs from an earlier architecture note, follow the repository shape first.
- If the current sprint plan emphasizes one lane, prefer work that helps that lane ship cleanly.

## Common example for this repository

The repository already has a meaningful AI-facing tool layer in `bb/tools/queries.py`. Future chat features should be designed to build on that layer instead of assuming a fully mature chat runtime is already present.
