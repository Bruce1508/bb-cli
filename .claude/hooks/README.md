# Hooks

This directory contains project-specific hook scripts for `bb-cli`.

## Scope

These scripts are wired through the project settings file:

- `.claude/settings.json`

This follows Claude Code's project-level hook model, where hooks declared in `.claude/settings.json` apply to the current repository.

## Hook scripts

### `scripts/guard-uv.sh`

Runs before Bash tool calls and checks for commands that drift from repository conventions.

Current behavior:
- flags direct `pip` usage
- flags `python -m pip`
- flags bare `pytest` when it is not invoked through `uv run`

The hook does not silently block the command. Instead, it returns a `PreToolUse` decision of `ask`, which surfaces the repository convention and lets the user confirm intentionally.

### `scripts/suggest-targeted-tests.sh`

Runs after successful `Edit` or `Write` tool calls and suggests small, relevant checks based on which paths were changed.

Current path groups:
- DB and tool layer: `bb/db.py`, `bb/tools/queries.py`, `bb/models/content.py`
- scraping lane: `bb/adapters/blackboard_ultra.py`, `selectors/blackboard_ultra.toml`, `bb/sync.py`
- CLI surface: `bb/cli.py`
- packaging: `pyproject.toml`

The hook adds repo-specific follow-up context rather than trying to run tests automatically.

## Design intent

These hooks are deliberately lightweight guardrails.

They are meant to:
- reinforce repo conventions
- reduce avoidable workflow drift
- suggest the smallest relevant verification step

They are not meant to become a heavy automation layer that interrupts normal work unnecessarily.
