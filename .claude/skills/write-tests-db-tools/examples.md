# write-tests-db-tools Examples

Use these patterns as a guide. Adjust them to the real caller and behavior under test.

## 1. Database behavior

Best for:
- migration behavior
- upsert logic
- query helpers in `bb/db.py`

Protect:
- row creation
- updates vs inserts
- ordering and filtering
- serialization-friendly values returned to callers

Typical scenarios:
- insert a new deadline and confirm it is returned by upcoming-deadlines logic
- upsert an existing grade and confirm update behavior rather than duplicate creation
- verify course-map lookup is case-insensitive where expected
- confirm download records remain queryable by course

## 2. Tool output contracts

Best for:
- functions in `bb/tools/queries.py`

Protect:
- JSON-friendly structure
- key names and shape
- graceful empty-state behavior
- consistency with underlying DB or cache-backed data

Typical scenarios:
- `get_upcoming_deadlines()` returns a list of dicts with stable keys
- `get_grades()` returns an empty list rather than crashing when DB state is missing
- `get_sync_status()` returns an error payload or sync stats consistently
- `list_downloaded_files()` respects optional course filtering

## 3. Content tree serialization

Best for:
- `bb/models/content.py`
- content-tree and content-item dict conversion

Protect:
- recursive child handling
- shape stability for cached content
- safe round-trip serialization and deserialization

Typical scenarios:
- `content_tree_to_dict()` preserves course code, Blackboard id, and item hierarchy
- `content_tree_from_dict()` rebuilds nested children correctly
- serialized content remains usable by search or chat-facing tools

## 4. Empty and degraded states

Best for:
- user-facing robustness
- future chat confidence

Protect:
- honest behavior when prerequisites are missing
- no silent fabrication when DB or cache is absent

Typical scenarios:
- missing DB returns empty lists or explicit error payloads as designed
- missing cache returns empty dict or no matches instead of stack traces
- unreadable PDF returns a structured error result rather than an exception leak

## 5. Regression tests after routing or grounding bugs

Best for:
- bugs discovered through `debug-tool-routing` or `verify-grounding`

Protect:
- the exact output condition that caused misleading AI-facing behavior

Typical scenarios:
- a tool used to omit a needed key and now includes it
- a partial-support path used to imply certainty and now returns a clearer contract
- a content search edge case now returns stable, grounded results

## Practical rule of thumb

For this repository, write tests that protect the contracts future chat behavior will rely on:

- DB-backed facts should stay queryable and stable
- tool outputs should stay predictable
- content-tree shapes should stay serializable
- empty and degraded states should stay honest
