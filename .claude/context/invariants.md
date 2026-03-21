# Invariants

These are repository rules that should remain true unless there is an explicit architectural decision to change them.

## Product and scope invariants

- The product is terminal-first.
- Current repository state is implementation truth.
- `PLAN.md` is delivery-priority truth for the active sprint.
- Finish current sprint commitments before expanding into v0.2 ideas.

## Runtime and workflow invariants

- Use `uv`-based repo workflows for running, testing, and packaging.
- Prefer minimal-impact changes that fit the existing architecture.
- When a request touches multiple lanes, identify the true owning path before editing.

## Data and grounding invariants

- Blackboard facts should be grounded in local database state, cached files, or tool outputs.
- AI-facing query outputs should stay JSON-friendly and predictable.
- Missing DB or cache state should be handled honestly and gracefully.
- Do not silently convert missing data into fabricated certainty.

## Scraping invariants

- Blackboard selectors belong in `selectors/blackboard_ultra.toml`.
- Selector fixes should be considered before broad parser rewrites.
- Scraping paths should preserve the current resilience pattern: primary selectors, fallback selectors, and constrained traversal.
- Snapshot save behavior in `bb/sync.py` is part of the debugging workflow when stream scraping yields zero items.

## Persistence invariants

- Schema and migration behavior in `bb/db.py` should remain coherent with all callers.
- Changes to persistence helpers should be evaluated for impact on CLI flows and AI-facing query helpers.
- Database-facing changes should preserve case-handling and serialization expectations already encoded in the repo.

## Future chat and AI invariants

- Day 10 `bb chat` should build on the existing tool layer rather than bypassing it.
- If a future chat feature needs new data access, prefer extending `bb/tools/queries.py` or adjacent data access logic instead of relying on prompt-only behavior.
