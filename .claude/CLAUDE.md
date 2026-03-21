# CLAUDE.md

This file provides project-specific guidance for Claude Code when working in this repository.

## Project Identity

`bb-cli` is a terminal-first Blackboard client for students. The current repository already implements the Day 1–9 foundation: CLI commands, SQLite persistence, iCal + Blackboard sync, course content caching, downloads, and an AI-facing query layer. The immediate delivery priority is Day 10: `bb chat`.

## Current Delivery Phase

- Treat the repository state as implemented truth.
- Treat `PLAN.md` as delivery-priority truth.
- The current sprint is complete through Day 9.
- Prioritize Day 10–14 deliverables before v0.2 ideas.
- If a requested change is outside the current plan, note it as future work instead of silently expanding scope.

## Non-Negotiable Rules

- Use `uv` for running, testing, and packaging workflows. Do not replace repo workflows with direct `pip` usage.
- Keep Blackboard data answers grounded in local data or tool results. Do not invent Blackboard facts.
- Keep selectors externalized in `selectors/blackboard_ultra.toml`. Do not hardcode fragile selectors into random call sites unless there is a strong reason.
- Prefer minimal-impact changes that fit the current architecture.
- When project brief, roadmap, and source diverge, trust the current repository state first.

## Repo Navigation by Path

- `pyproject.toml` — package metadata, entrypoint, build config, dev tooling
- `bb/cli.py` — Typer command surface and user-facing orchestration
- `bb/db.py` — SQLite schema, migrations, persistence helpers, sync log, downloads
- `bb/sync.py` — iCal retry flow, activity-stream sync, grade sync, snapshot save
- `bb/adapters/blackboard_ultra.py` — Blackboard auth, session restore, scraping, selector-driven parsing, content-tree traversal
- `selectors/blackboard_ultra.toml` — runtime selector source for Blackboard scraping
- `bb/tools/queries.py` — AI-facing query surface returning JSON-friendly results
- `bb/models/content.py` — content tree dataclasses and serialization helpers

## Change Rules by Lane

### CLI and command behavior
Start in `bb/cli.py`. Check whether the change also affects persistence in `bb/db.py`, sync behavior in `bb/sync.py`, or cached content behavior.

### Database, schema, or persistence
Start in `bb/db.py`. Review migrations, query helpers, and all callers in `bb/cli.py` and `bb/tools/queries.py`.

### Blackboard scraping or selector breakage
Inspect `bb/adapters/blackboard_ultra.py` and `selectors/blackboard_ultra.toml` together. Prefer selector fixes before broad parser rewrites. Check `bb/sync.py` snapshot behavior when stream scraping returns zero items.

### AI-facing data access and future chat behavior
Start in `bb/tools/queries.py`. Ensure outputs stay JSON-serializable, missing DB/cache states are handled gracefully, and response logic stays grounded in actual data.

### Course content, cache, and downloads
Inspect `bb/models/content.py`, the course/download commands in `bb/cli.py`, and the Blackboard content scraping logic in `bb/adapters/blackboard_ultra.py`.

## Verification Rules

- CLI changes: verify the affected command flow and any impacted tables or cache behavior.
- DB changes: verify schema compatibility, caller expectations, and regression risk.
- Scraping changes: verify the selector path, fallback behavior, and minimum viable fix.
- Tool-layer changes: verify JSON shape, empty-state behavior, and alignment with the underlying database or cached files.
- Sprint-facing AI/chat changes: prefer extending the tool surface before compensating with prompt-only behavior.

## Skills and Subagents

Use `.claude/context/` for project memory, `.claude/skills/` for repeatable workflows, and `.claude/agents/` for specialized review or investigation once those are added. Keep this file constitutional and path-aware; move long checklists and playbooks into skills or context files.

## Git Rules

- **NEVER commit `docs/` or `tasks/`** — internal planning files (specs, plans, brainstorming). They are in `.gitignore`. If `git add` warns "ignored file", stop immediately — never force-add.
- **`git filter-repo` removes remote** — after running it, always re-add: `git remote add origin git@github.com:Bruce1508/bb-cli.git`
- **Force push only after intentional history rewrite** — use `git push --force origin main` only after `git filter-repo`. Normal pushes use `--force-with-lease`.

## Python / Testing Gotchas (learned Day 8–9)

- **`pdfplumber` pages outside `with` block** — `pdf.pages` raises after context exits. Always capture `page_count = len(pdf.pages)` INSIDE `with pdfplumber.open() as pdf:`.
- **`iterdir()` on missing dir** — `Path.iterdir()` raises `FileNotFoundError` if dir doesn't exist. Guard: `if not path.exists(): return ...` before iterating.
- **`httpx.stream()` needs method arg** — `client.stream("GET", url)`, not `client.stream(url)`. Also: `Content-Length` is a string — cast: `int(response.headers.get("content-length", 0))`.
- **`patch()` needs module-level import** — `patch("bb.tools.queries.pdfplumber.open")` requires `import pdfplumber` at module level. Lazy imports inside functions don't exist as attributes at patch time.
- **`or` vs `is not None`** — `x or default` treats empty list/string/0 as falsy. Use `x if x is not None else default` when "provided but empty" is a valid value.
- **Library classes must not have UI deps** — never put `typer.confirm` / `input()` inside library classes (`Downloader`, etc.). That's the CLI layer's responsibility; mixing them breaks non-TTY usage and testing.
- **Partial file cleanup on failure** — on download error, always `dest_path.unlink(missing_ok=True)` in except clauses so corrupt partial files don't accumulate silently.
- **`uv pip install -e .` .pth bug** — hatchling generates `_bb_cli.pth` without trailing newline; Python skips it. Fix: `printf '/path/to/bb-cli\n' > .venv/lib/python3.13/site-packages/_bb_cli.pth`.
- **`webbrowser.open(None)`** — silently opens `"None"` as a URL. Always guard: `if item.url is None: raise typer.Exit(1)` before calling.
