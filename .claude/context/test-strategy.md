# Test Strategy

This file captures testing guidance that matches the current repository rather than an imagined future architecture.

## Primary testing paths

Inspect these first when planning tests:

- `pyproject.toml`
- `bb/db.py`
- `bb/tools/queries.py`
- `bb/models/content.py`
- `bb/sync.py`
- `bb/adapters/blackboard_ultra.py`
- `tests/`

## Core testing principles

- Prefer tests that protect real repository contracts.
- Use real SQLite behavior when persistence or query behavior is the thing under test.
- Keep AI-facing tool outputs predictable, JSON-friendly, and explicitly asserted.
- Cover empty-state and degraded-state behavior deliberately.
- Avoid mocks that erase the exact DB, serialization, or scraping behavior the repo depends on.

## What to protect most

### 1. Database and persistence contracts

Focus on:

- migrations staying coherent
- upsert behavior
- query correctness
- sync-log and cooldown-related persistence behavior
- course-map and downloads behavior

These are centered in `bb/db.py`.

### 2. Tool output contracts

Focus on:

- stable dict/list shapes from `bb/tools/queries.py`
- graceful behavior when DB or cache is missing
- consistency between tool outputs and the underlying DB or cached data

These tests matter directly for Day 10–11 chat quality.

### 3. Content tree serialization

Focus on:

- round-trip serialization in `bb/models/content.py`
- nested child integrity
- safe shapes for cache-backed and AI-facing access

### 4. Sync and scraping behavior

Focus on:

- iCal retry and parse paths in `bb/sync.py`
- snapshot behavior when stream scraping yields zero items
- selector-driven adapter behavior in `bb/adapters/blackboard_ultra.py`

## Practical test-level guidance

### Use narrow tests when

- a serializer or helper has a clear local contract
- a single output shape is the thing being protected
- the failure mode does not depend on broader orchestration

### Use repository-level tests when

- the behavior depends on SQLite state
- upserts, filters, ordering, or persistence semantics matter
- a tool contract depends on real stored data

### Use regression-focused tests when

- a bug in routing, grounding, or scraping was previously observed
- the failure mode could reappear through an innocent-looking refactor

## Empty and degraded states to test on purpose

- missing DB
- missing cache
- unreadable file content
- partial support where a tool can only answer part of the request
- stream scraping that returns zero items and triggers snapshot behavior

## Sprint-aware testing priority

Because the sprint is complete through Day 9 and moving into Day 10–14, prioritize tests that improve confidence in:

- tool-backed chat behavior
- grounded AI-facing answers
- stable data and serialization contracts
- scraper resilience without broad rewrites

## Anti-patterns

Avoid:

- testing a prompt or imagined future runtime while ignoring the current tool/data foundation
- over-mocking persistence behavior that should be tested against real SQLite semantics
- asserting vague behavior instead of explicit output contracts
- adding broad test complexity when a smaller contract test would protect the failure mode directly
