# Hooks

This directory holds operational guardrails for the repository.

## Current status

The hook scripts in `scripts/` are intentionally implemented before wiring a final `hooks.json` configuration.

Why:
- the repository-level `.claude/` guidance, context files, skills, and agents are already usable
- the hook command scripts themselves are straightforward and repo-specific
- the exact hook configuration schema should be verified against the current Claude Code hook format before committing a final `hooks.json`

## Intended hooks

### guard-uv.sh

Purpose:
- catch or warn on `pip install`, `python -m pip`, or bare `pytest` usage that drifts from repo conventions

Repo rationale:
- this repository uses `uv`-based workflows
- replacing those workflows casually increases inconsistency and release risk

### suggest-targeted-tests.sh

Purpose:
- suggest smaller, relevant test commands based on which repo paths were changed

Repo rationale:
- the repository has clear lanes: DB/tool layer, scraping lane, CLI surface, package/release layer
- targeted test suggestions are more practical than blindly recommending the full test suite on every edit

## Planned follow-up

Once the final Claude Code hook configuration format is re-verified, add:

- `.claude/hooks/hooks.json`

That config should wire the scripts to the most appropriate guardrail events without over-automating the repo.
