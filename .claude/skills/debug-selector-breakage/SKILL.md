---
name: debug-selector-breakage
description: Investigates Blackboard scraping failures caused by selector drift, DOM changes, or confusion between auth/session issues and selector issues. Use when stream, grades, course-list, or course-content scraping stops behaving as expected.
---

# Purpose

Use this skill when Blackboard scraping fails or returns weak results and you need a disciplined way to diagnose the cause.

This repository already has a selector-driven scraping design with fallback patterns, session handling, and snapshot behavior. The goal of this skill is to preserve that design and fix the smallest real breakage first.

# Primary paths

Inspect these first:

- `bb/adapters/blackboard_ultra.py`
- `selectors/blackboard_ultra.toml`
- `bb/sync.py`
- `bb/cli.py`
- `.claude/context/architecture-map.md`
- `.claude/context/invariants.md`
- `.claude/context/sprint-status.md`

# When to use

Use this skill when:

- activity-stream scraping suddenly returns zero items
- grade scraping starts missing rows or fields
- course-list discovery breaks
- course-content scraping fails after Blackboard UI drift
- you need to distinguish selector breakage from session/auth problems
- a scraping fix must be made without destabilizing the rest of the lane

Do not use this skill for pure tool-routing problems or packaging issues.

# Diagnosis principles

- Check session/auth reality before blaming selectors blindly.
- Check selector files before broad parser rewrites.
- Preserve the current resilience strategy of primary selector plus fallback selector.
- Use the repository's existing snapshot/debug behavior when stream scraping yields zero items.
- Prefer the smallest fix that restores reliable extraction.

# Workflow

1. Identify the failing scraping surface.
   - activity stream
   - grades page
   - course list
   - course content

2. Identify the likely failure class.
   - session expired or invalid
   - selector drift
   - DOM shape change
   - parser assumption mismatch
   - upstream page did not load the expected content

3. Inspect `bb/adapters/blackboard_ultra.py`.
   - find the relevant fetch method
   - inspect current selector usage and fallback logic
   - inspect circuit breakers or traversal assumptions that may now be exposed

4. Inspect `selectors/blackboard_ultra.toml`.
   - confirm whether the primary selector likely drifted
   - check whether a fallback exists already
   - decide whether the change belongs in TOML rather than code

5. Inspect related runtime behavior.
   - for stream scraping, inspect `bb/sync.py` snapshot handling
   - for command-level symptoms, inspect `bb/cli.py` only after understanding adapter behavior

6. Choose the smallest correct fix.
   - update selector
   - add or refine fallback selector
   - adjust parser assumption in adapter code
   - improve degraded behavior or diagnostics

7. Re-check scope.
   - do not let a localized selector issue trigger an unnecessary architecture rewrite

# Verification

Before considering the issue resolved, confirm:

- the actual failing lane was identified correctly
- the fix matches selector reality or session reality rather than guesswork
- selector externalization is preserved where possible
- fallback behavior remains coherent
- the change minimizes regression risk to the rest of the scraping lane

# Output expectations

When using this skill, produce:

- the scraping surface that failed
- the likely failure class
- the repo paths inspected
- the smallest correct fix
- any future hardening ideas that should remain separate from the immediate repair

Then consult `playbook.md` for repo-specific debugging guidance.
