# Sprint Status

## Active planning source

Use `PLAN.md` as the delivery-priority source for the current sprint.

## Current status

The sprint is complete through Day 9.

That means the repository already has the foundational work for:

- CLI setup and command surface
- local database and migrations
- iCal import and Blackboard sync
- auth and session handling
- grades, announcements, and status flows
- course discovery and content browsing
- caching, downloads, file opening, and file-reading tools

## Immediate milestone

The next priority is Day 10: `bb chat`.

Claude should optimize for enabling a strong chat/runtime layer on top of the existing tool and data foundation.

## Next priorities after Day 10

- Day 11: chat polish, tool selection quality, AI-facing helper expansion
- Day 12: MCP-facing work, tests, docs alignment
- Day 13–14: packaging, release readiness, ship discipline

## Scope discipline

If an idea is not part of the active plan and is not required to complete the current sprint, treat it as future work instead of silently folding it into the current milestone.

## Practical interpretation for Claude Code

- Current source state explains what exists now.
- `PLAN.md` explains what should be delivered next.
- Prefer work that reduces risk for Day 10–14 over unrelated architecture exploration.
