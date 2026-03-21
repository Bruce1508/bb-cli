---
name: feature-mcp-server
description: Designs or implements MCP-facing work for bb-cli by exposing the existing grounded tool layer safely. Use when moving into the Day 12 MCP milestone or evaluating how current repo capabilities should be exposed to Claude Desktop or other MCP clients.
---

# Purpose

Use this skill when working on the MCP-facing layer for `bb-cli`.

The current repository already has an AI-facing tool foundation in `bb/tools/queries.py`. MCP work should expose that foundation coherently instead of inventing a second parallel data-access layer.

# Primary paths

Inspect these first:

- `bb/tools/queries.py`
- `bb/db.py`
- `bb/models/content.py`
- `bb/cli.py`
- `pyproject.toml`
- `PLAN.md`
- `.claude/context/project-overview.md`
- `.claude/context/invariants.md`
- `.claude/context/roadmap-vs-current-state.md`
- `.claude/context/sprint-status.md`

If MCP-specific source files are added later, include them after understanding the current tool surface and data contracts.

# When to use

Use this skill when:

- planning the Day 12 MCP milestone
- deciding which current capabilities should be exposed as MCP tools
- reviewing whether the current tool surface is suitable for MCP exposure
- deciding whether a new MCP-facing need should be solved by refining existing tools first
- evaluating how to keep MCP behavior grounded, consistent, and minimal-risk

Do not use this skill for pure selector debugging or packaging-only work.

# Design principles

- Treat the current tool layer as the main bridge between local data and AI-facing behavior.
- Prefer reusing or refining existing tool contracts over introducing a second independent query system.
- Keep Blackboard-facing information grounded in repo-backed data.
- Distinguish implemented source state from planned MCP architecture.
- Choose the smallest MCP-facing design that supports the active sprint.

# Workflow

1. Confirm the MCP-facing requirement.
   - What should an MCP client be able to ask or do?
   - Is this already covered by an existing tool?

2. Audit the current tool surface.
   - Inspect `bb/tools/queries.py`.
   - Review tool names, docstrings, arguments, output shapes, and empty-state behavior.

3. Check the backing data path.
   - Confirm the underlying DB, content-tree, or file-backed behavior in `bb/db.py` and `bb/models/content.py`.

4. Choose the smallest correct exposure layer.
   - reuse an existing tool as-is
   - refine a current tool for clearer AI-facing use
   - add a narrowly-scoped new tool
   - only then consider wider MCP-surface changes

5. Check product fit.
   - Does the proposed exposure help the terminal-first student workflow?
   - Does it preserve the product promise of grounded Blackboard help?

6. Check sprint fit.
   - Confirm the work aligns with Day 12 rather than expanding into unrelated v0.2 ideas.

# Verification

Before considering the MCP-facing design complete, confirm:

- the proposal builds on the current tool and data foundation
- the exposed capability is grounded in repo-backed data
- the solution does not assume source files or runtime layers that do not yet exist
- the result supports the Day 12 milestone with minimal architecture drift

# Output expectations

When using this skill, produce:

- the MCP-facing capability under consideration
- the current tool/data paths inspected
- the recommended exposure strategy
- any tool refinements needed first
- any future work that should remain explicitly out of scope for the current sprint

Then consult `checklist.md` before considering the work ready.
