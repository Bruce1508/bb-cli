---
name: feature-bb-chat
description: Builds or extends bb chat features on top of the existing tool and data foundation. Use when implementing Day 10 or Day 11 chat functionality, improving tool usage, or shaping the user-facing chat experience.
---

# Purpose

Use this skill when working on `bb chat` or any closely related AI-facing behavior for `bb-cli`.

This repository already has a strong data and tool foundation through Day 9. The chat layer should be designed to sit on top of that foundation rather than bypassing it.

# Primary paths

Start with these files before designing a solution:

- `bb/tools/queries.py`
- `bb/db.py`
- `bb/models/content.py`
- `bb/cli.py`
- `PLAN.md`
- `.claude/context/project-overview.md`
- `.claude/context/invariants.md`
- `.claude/context/sprint-status.md`

If a dedicated chat runtime is added later, include that path in the investigation, but do not assume it already exists just because it appears in planning notes.

# When to use

Use this skill when:

- adding the first version of `bb chat`
- extending chat capabilities for deadlines, grades, announcements, course content, or downloaded files
- deciding whether a new user request needs a new tool, a better tool docstring, or a chat-layer change
- improving fallback behavior when tool usage is uncertain or partial
- reviewing whether a chat answer is properly grounded in real data

Do not use this skill for pure scraping fixes, packaging work, or schema-only changes unless they directly block chat delivery.

# Design principles

- Build chat on top of the existing tool layer first.
- Prefer adding or refining tools over compensating with prompt-only behavior.
- Treat Blackboard facts as grounded data, not as content for free-form improvisation.
- Be honest when the current tool surface cannot answer a question with confidence.
- Keep the terminal-first product identity intact.

# Workflow

1. Confirm the chat behavior being added or fixed.
   - Is it a new user intent?
   - Is it a routing problem?
   - Is it a missing data-access problem?
   - Is it a response-format problem?

2. Inspect the current tool surface in `bb/tools/queries.py`.
   - Determine whether the request can already be satisfied.
   - Check output shape, naming, and empty-state behavior.
   - Review docstrings as part of the model interface.

3. Inspect underlying data sources.
   - Use `bb/db.py` for deadlines, grades, announcements, sync status, downloads.
   - Use `bb/models/content.py` plus cached-content helpers for course content shape.

4. Choose the smallest correct layer to change.
   - If data access is missing, extend the tool surface.
   - If the tool exists but is awkward for chat, improve its interface or shape.
   - If the tool is sufficient, keep the chat change small.

5. Plan the response behavior.
   - What should happen when data exists?
   - What should happen when data is missing?
   - What should happen when only partial support exists?

6. Verify groundedness.
   - Every Blackboard-facing claim should trace back to a tool result, DB-backed value, or cached-file content.
   - If the chat layer must infer something, mark it clearly as inference.

7. Document any tool gap discovered.
   - If the current sprint cannot include the full improvement, name it as follow-up instead of hiding it.

# Verification

Before considering the work complete, confirm:

- the solution builds on repo reality rather than idealized architecture
- the chosen layer is the smallest correct layer
- the resulting answer path stays grounded in actual tool/data outputs
- empty states remain honest and useful
- the change helps Day 10 or Day 11 delivery rather than adding unrelated complexity

# Output expectations

When using this skill, produce:

- a short diagnosis of the problem type
- the repo paths inspected
- the chosen layer to modify
- the expected grounded behavior
- any follow-up gaps or risks

Then use `rubric.md` to review the result.
