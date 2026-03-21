# Scraping Notes

This file captures the repository's current scraping design and the assumptions that matter when repairing or extending it.

## Primary scraping paths

Inspect these first:

- `bb/adapters/blackboard_ultra.py`
- `selectors/blackboard_ultra.toml`
- `bb/sync.py`
- `bb/cli.py`

## Current scraping design

The Blackboard scraping lane is centered on `bb/adapters/blackboard_ultra.py`.

That adapter currently owns:

- headed authentication flow
- encrypted session reuse
- activity-stream scraping
- grades scraping
- course-list scraping
- course-content scraping

Selectors are loaded from `selectors/blackboard_ultra.toml` and should be treated as part of the scraping system rather than as passive configuration.

## Key resilience patterns already present

### 1. Selector externalization

Selector definitions live outside the adapter code where possible.

Practical consequence:
- if a Blackboard UI change only shifts DOM selectors, prefer updating selector definitions before broad parser rewrites

### 2. Primary and fallback selector use

Several scraping paths already try a primary selector and then a fallback selector.

Practical consequence:
- keep this pattern intact when fixing drift
- do not simplify the lane by removing fallback coverage casually

### 3. Session-aware behavior

Scraping failures are not always selector failures.

Practical consequence:
- confirm whether the page is in the expected authenticated state before diagnosing selector drift
- treat session validity and selector correctness as separate questions first

### 4. Snapshot-assisted debugging

`bb/sync.py` preserves useful behavior for stream scraping when zero items are returned.

Practical consequence:
- use the snapshot/debug path before making speculative scraping rewrites
- let the saved page shape guide the diagnosis when possible

### 5. Circuit-breaker style limits

The adapter includes limits such as max processed items or traversal depth.

Practical consequence:
- partial failures may come from traversal assumptions or safety limits, not just broken selectors

## Common failure classes

- invalid or expired session state
- selector drift after Blackboard UI changes
- DOM shape change that breaks parser assumptions
- content present but nested differently than expected
- page loading behavior that prevents the expected container from appearing

## Repair guidance

When fixing scraping behavior:

1. identify the exact scraping surface that failed
2. inspect the corresponding adapter method first
3. inspect selector definitions second
4. use the smallest fix that restores reliability
5. keep selector externalization and fallback strategy intact where possible

## What not to do

Avoid:

- assuming every scraping failure is a selector issue
- rewriting the adapter broadly before confirming the failure class
- mixing session repair and selector repair when only one is needed
- changing unrelated scraping lanes while fixing one localized breakage

## Sprint-aware interpretation

The scraping lane is part of the Day 9 foundation that later chat features will rely on.

That means scraping repairs should favor stability, diagnosability, and small corrections over ambitious redesigns during the active sprint.
