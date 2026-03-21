---
name: debug-tool-routing
description: Investigates why an AI-facing request uses the wrong tool, skips a needed tool, or gets weak results from the current tool surface. Use when improving tool selection or diagnosing chat quality issues.
---

# Purpose

Use this skill when a user-facing AI flow does not interact well with the repository's current tool layer.

The goal is to diagnose tool-routing issues systematically instead of guessing whether the problem is in the prompt, tool docstrings, tool outputs, underlying data access, or the absence of a needed tool.

# Primary paths

Inspect these first:

- `bb/tools/queries.py`
- `bb/db.py`
- `bb/models/content.py`
- `PLAN.md`
- `.claude/context/architecture-map.md`
- `.claude/context/invariants.md`
- `.claude/context/roadmap-vs-current-state.md`

If a future chat runtime file exists, include it only after understanding the current tool surface.

# When to use

Use this skill when:

- a chat request chooses the wrong tool
- a chat request fails to use an obvious tool
- a tool is technically correct but awkward for model use
- a user request is only partially answerable and the system handles it poorly
- you need to decide whether the fix belongs in docstrings, output shape, data access, or a new tool

# Common failure modes

- the correct tool exists but its docstring is weak or ambiguous
- the tool output is valid JSON but not shaped usefully for model consumption
- the data path under the tool is incomplete or misleading
- the request spans multiple tools but the system lacks a clean strategy
- the needed capability is genuinely missing from the tool surface

# Workflow

1. Capture the request or user intent.
   - What is the user really asking?
   - Is it a single-intent request or a mixed request?

2. Check whether the request is already toolable.
   - Identify the closest existing tool in `bb/tools/queries.py`.
   - Review its docstring as part of the model interface.

3. Inspect output shape.
   - Is the output JSON-friendly?
   - Is it too sparse, too noisy, or missing important context?
   - Does the empty-state behavior help or confuse?

4. Inspect the underlying data path.
   - If the tool reads DB-backed data, inspect `bb/db.py`.
   - If the tool reads content-tree data, inspect `bb/models/content.py` and relevant cache behavior.

5. Decide the smallest correct fix.
   - Docstring refinement
   - Output-shape refinement
   - Tool extension
   - New tool
   - Future chat-layer refinement after tools are solid

6. Re-check grounding.
   - Do not improve routing by making the model freer to improvise unsupported facts.

# Decision guidance

Prefer this order when choosing a fix:

1. improve docstring clarity
2. improve output shape
3. improve underlying data access
4. add a new tool
5. only then consider broader chat-layer logic

# Verification

Before considering the routing issue resolved, confirm:

- the chosen fix matches the real cause
- the updated tool surface is still grounded in actual data
- the tool output is practical for model use
- empty and partial states are handled honestly
- the change reduces sprint risk for Day 10–11

# Output expectations

When using this skill, produce:

- the request or intent being analyzed
- the most likely failure mode
- the repo paths inspected
- the smallest correct fix
- any remaining limitation that should become follow-up work

Then use `rubric.md` to evaluate the result.
