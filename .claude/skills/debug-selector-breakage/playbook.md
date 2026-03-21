# debug-selector-breakage Playbook

Use this playbook after identifying that a Blackboard scraping lane is failing.

## 1. First question: is this really a selector problem?

Before editing selectors, ask:

- Is the saved session still valid?
- Did the page load the expected authenticated content?
- Is the user being redirected or shown a partial page?

If the page is not in the expected authenticated state, the problem may be session-related rather than selector-related.

## 2. Check the owning adapter method

In `bb/adapters/blackboard_ultra.py`, find the exact method involved:

- `fetch_activity_stream()`
- `fetch_grades()`
- `fetch_course_list()`
- `fetch_course_content()`

Then inspect:

- primary selector usage
- fallback selector usage
- assumptions about required elements
- traversal depth or item limits if the failure is partial rather than total

## 3. Check the selector file before code rewrites

Inspect `selectors/blackboard_ultra.toml` next.

Look for:

- a primary selector that likely drifted
- a missing fallback that should exist
- a selector name that no longer matches the adapter's expectation

If the breakage can be fixed in the TOML file cleanly, prefer that over broad adapter changes.

## 4. Use stream snapshot behavior when relevant

If the problem is activity-stream scraping returning zero items, inspect `bb/sync.py` and any saved snapshot behavior first.

This can help answer:

- did the page shape drift?
- did the expected container disappear?
- did the adapter fetch a page that looked authenticated but structurally changed?

## 5. Decide the smallest correct fix

Choose among:

- update the primary selector
- add or refine a fallback selector
- tighten or relax adapter assumptions
- improve diagnostics for a known degraded case

Avoid:

- large rewrites before confirming the breakage class
- mixing session fixes with selector fixes unless both are truly involved
- changing unrelated scraping lanes while repairing one lane

## 6. Protect the design pattern

This repository already uses a sensible pattern:

- selectors externalized in TOML
- adapter methods own scraping logic
- fallback behavior exists in key places
- stream snapshots help debug zero-item failures

A fix should preserve that pattern whenever possible.

## 7. Name follow-up hardening separately

If a scraping incident reveals future hardening work, record it separately instead of inflating the immediate fix.

Examples:

- adding better diagnostics
- expanding fallback coverage
- refining selector naming consistency
- improving tests around a newly fragile lane
