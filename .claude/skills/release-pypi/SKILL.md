---
name: release-pypi
description: Plans or reviews PyPI release work for bb-cli, focusing on packaging correctness, installability, CLI readiness, and current sprint release discipline. Use when preparing the Day 13–14 release path.
---

# Purpose

Use this skill when preparing `bb-cli` for packaging and release.

The goal is to keep release work grounded in the current repository state: packaging metadata, CLI entrypoints, test confidence, and the Day 13–14 sprint scope.

# Primary paths

Inspect these first:

- `pyproject.toml`
- `bb/cli.py`
- `PLAN.md`
- `tests/`
- `.claude/context/project-overview.md`
- `.claude/context/invariants.md`
- `.claude/context/sprint-status.md`
- `.claude/context/roadmap-vs-current-state.md`
- `.claude/context/test-strategy.md`

If build or release automation files are added later, include them after understanding the current package and CLI contract first.

# When to use

Use this skill when:

- preparing the Day 13–14 release milestone
- reviewing whether the package metadata is coherent
- checking CLI entrypoint readiness
- validating whether tests cover release-critical repo behavior
- deciding the smallest work needed to make `bb-cli` realistically shippable

Do not use this skill for broad feature design or scraping-only debugging.

# Release principles

- Start from the real package and CLI shape, not a future wish list.
- Prefer release readiness over late-sprint architecture expansion.
- Ensure the terminal-first user experience is reflected in packaging and entrypoint behavior.
- Keep scope aligned with the active sprint.

# Workflow

1. Inspect package metadata in `pyproject.toml`.
   - project name
   - versioning
   - dependencies
   - script entrypoint
   - build backend

2. Inspect the CLI contract in `bb/cli.py`.
   - confirm user-facing commands align with what the package is meant to ship
   - identify any obviously release-blocking inconsistencies

3. Inspect release-critical test coverage.
   - focus on DB/tool/sync/content foundations that the product promise depends on
   - check whether high-risk paths have at least basic protection

4. Identify the smallest remaining release blockers.
   - packaging issue
   - installability issue
   - CLI readiness issue
   - missing test coverage on a release-critical contract
   - sprint-scope mismatch

5. Separate blockers from enhancements.
   - keep v0.1 release work distinct from post-release improvements

# Verification

Before considering release planning or review complete, confirm:

- package metadata matches current repo reality
- the CLI entrypoint and command surface are coherent
- release blockers are identified concretely rather than vaguely
- current-sprint release work is separated from future improvements
- the output supports a realistic Day 13–14 ship path

# Output expectations

When using this skill, produce:

- the release-critical paths inspected
- the current release-readiness assessment
- concrete blockers, if any
- the smallest release-ready path forward
- any deferred improvements that should remain outside the active sprint

Then consult `checklist.md` to complete the review.
