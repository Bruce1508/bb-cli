---
name: write-tests-db-tools
description: Designs or reviews tests for the database, tool layer, and related serialized content shapes. Use when changing persistence, query helpers, JSON outputs, cache-backed content access, or any repo logic that future chat behavior depends on.
---

# Purpose

Use this skill when a change touches the repository's data and tool foundation and needs robust regression coverage.

This repository's chat and AI-facing behavior will only be as trustworthy as the DB and tool layer beneath it. The goal of this skill is to keep tests aligned with real repo behavior rather than abstract mocks that miss the failure mode.

# Primary paths

Inspect these first:

- `bb/db.py`
- `bb/tools/queries.py`
- `bb/models/content.py`
- `bb/sync.py`
- `pyproject.toml`
- `tests/`
- `.claude/context/test-strategy.md`
- `.claude/context/invariants.md`

If a change also touches CLI or scraping flows, include the related caller path after understanding the DB/tool contract first.

# When to use

Use this skill when:

- changing migrations or persistence helpers in `bb/db.py`
- changing output shapes in `bb/tools/queries.py`
- adding or refining content-tree serialization logic
- testing missing DB, missing cache, or partial-support behavior
- adding regression tests after a tool-routing or grounding bug
- validating that a change helps Day 10–14 without weakening the foundation

Do not use this skill for pure UI copy changes or repo tasks that do not interact with data or tool behavior.

# Testing principles

- Prefer tests that exercise real repository behavior.
- Use real SQLite behavior where that is the thing under test.
- Keep JSON output contracts explicit.
- Test empty-state and failure-state behavior deliberately.
- Avoid mocks that erase the very behavior the repository relies on.

# Workflow

1. Identify the exact contract being protected.
   - DB schema or migration behavior
   - query helper behavior
   - JSON output shape
   - cache/content-tree serialization
   - missing-data handling

2. Find the owning implementation path.
   - `bb/db.py` for schema, migrations, and persistence
   - `bb/tools/queries.py` for AI-facing contracts
   - `bb/models/content.py` for content tree serialization
   - `bb/sync.py` when a data-ingestion path affects persistence or snapshots

3. Choose the right test level.
   - unit-style test for a narrow serializer or helper
   - repository-level test for DB-backed behavior
   - contract-style test for JSON outputs and empty states

4. Write the smallest set of tests that protects the behavior.
   - happy path
   - empty path
   - failure or degraded path
   - regression-specific path if applicable

5. Check that the test reflects repo reality.
   - Avoid assumptions that contradict current schema or output shape.
   - Avoid mocks that hide SQLite, serialization, or file-shape behavior.

6. Tie the test back to the product promise.
   - Ask whether the test protects grounded student-facing behavior or future chat confidence.

# Verification

Before considering the test work complete, confirm:

- the tests target the real owning path
- the tests protect the data or tool contract that future chat behavior depends on
- JSON output expectations are explicit
- empty and failure states are covered where they matter
- the test strategy fits the current repo rather than an imagined future architecture

# Output expectations

When using this skill, produce:

- the contract being protected
- the repo paths under test
- the chosen test level
- the specific scenarios covered
- any meaningful gaps still left as follow-up work

Then consult `examples.md` for repo-specific patterns.
