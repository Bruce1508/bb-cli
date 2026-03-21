# release-pypi Checklist

Use this checklist when reviewing whether `bb-cli` is ready for the Day 13–14 release path.

## Package reality

- Does `pyproject.toml` match the actual repository state?
- Are the package name, dependencies, and entrypoint coherent?
- Is the release plan based on what the repo really ships today?

## CLI readiness

- Does `bb/cli.py` expose a coherent terminal-first command surface?
- Are obvious release-blocking command inconsistencies identified?
- Is the package entrypoint aligned with the current CLI contract?

## Foundation confidence

- Are the DB, tool, sync, and content foundations protected enough for a release candidate?
- Are missing or degraded states handled honestly enough for users?
- Are there any release-critical gaps that should block a Day 13–14 ship?

## Sprint discipline

- Does the release path stay within current sprint scope?
- Are future improvements separated cleanly from true blockers?
- Is the plan realistic for v0.1 rather than a hidden v0.2 expansion?

## Output quality

- Does the release assessment name specific blockers instead of vague concerns?
- Does it identify the smallest realistic path to release readiness?
- Are deferred improvements explicitly listed rather than mixed into current release work?
