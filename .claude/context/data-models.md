# Data Models

This file summarizes the data shapes that matter most when working on the current repository.

## Primary model and storage paths

Inspect these first:

- `bb/db.py`
- `bb/models/content.py`
- `bb/adapters/blackboard_ultra.py`
- `bb/tools/queries.py`

## Database-backed Blackboard entities

The repository currently centers on these stored concepts:

### Deadlines

Used for upcoming work and sync-backed due-date behavior.

Key expectations:
- associated with a course code
- include a title
- include a due date/time value
- carry a source such as iCal or stream-backed extraction

These are persisted and queried through `bb/db.py`, then surfaced to AI-facing behavior through `bb/tools/queries.py`.

### Announcements

Used for course updates and recent-news style behavior.

Key expectations:
- associated with a course code
- have a title and body-related content
- include posted time information
- may have read/unread semantics

These are persisted in `bb/db.py` and surfaced through `bb/tools/queries.py`.

### Grades
n
Used for assignment results, score reporting, and academic status questions.

Key expectations:
- associated with a course code
- include assignment/item name
- may include score and out-of values
- include a status such as graded, submitted, or pending

These are persisted in `bb/db.py` and surfaced through `bb/tools/queries.py`.

### Course mapping

Used to connect human-readable course codes to Blackboard internal course ids.

Key expectations:
- course code remains the user-facing handle
- Blackboard internal id is used for scraping and outline access

This is stored in `bb/db.py` and used by course-content flows in `bb/cli.py` and `bb/adapters/blackboard_ultra.py`.

### Downloads

Used to track files downloaded to the local `~/.bb/files/` structure.

Key expectations:
- associated with a course
- include filename and path
- may include size metadata
- support listing/filtering behavior

These are stored in `bb/db.py` and surfaced through `bb/tools/queries.py`.

## Content tree models

Defined in `bb/models/content.py`.

### ContentItem

Represents a node in course content.

Key expectations:
- has a type such as module, file, folder, discussion, link, or assignment
- has a title
- may have a view URL
- may have a download URL
- may have nested children

### ContentTree

Represents course-scoped content as a structured hierarchy.

Key expectations:
- tied to an uppercase course code
- tied to a Blackboard course id
- includes scrape timestamp information
- holds a list of top-level content items

These shapes matter because search, cache behavior, downloads, and future chat flows all rely on them remaining stable and serializable.

## AI-facing contract shapes

The current tool layer in `bb/tools/queries.py` typically returns:

- lists of dicts
- single dict payloads
- explicit empty results when data is missing
- structured error payloads in some failure cases

This means model-facing behavior depends more on stable output shape than on rich custom classes.

## Practical guidance

When changing data behavior:

- identify whether the source of truth is DB-backed or cache/content-tree-backed
- keep serialization and JSON-facing shape in mind early
- treat model-facing output shape as part of the contract, not just an implementation detail
