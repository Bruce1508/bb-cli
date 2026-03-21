---
name: verify-grounding
description: Reviews AI-facing behavior to ensure Blackboard facts remain grounded in local data, cached files, or tool results. Use when validating chat behavior, tool-backed answers, or any AI-generated Blackboard response.
---

# Purpose

Use this skill to verify that an AI-facing answer or workflow stays grounded in actual repository-backed data.

This repository's core promise is practical help rooted in real Blackboard information. The role of this skill is to stop silent fabrication, unsupported certainty, and prompt-only overreach.

# Primary paths

Inspect these first:

- `bb/tools/queries.py`
- `bb/db.py`
- `bb/models/content.py`
- `PLAN.md`
- `.claude/context/invariants.md`
- `.claude/context/project-overview.md`
- `.claude/context/roadmap-vs-current-state.md`

If validating a future chat runtime, include it after confirming the supporting data and tool path.

# When to use

Use this skill when:

- reviewing a new or changed `bb chat` response flow
- checking whether a tool-backed answer is too confident
- validating that Blackboard facts are tied to real data access
- deciding how to phrase uncertainty, missing data, or partial support
- auditing a response that sounds plausible but may not be fully supported

# Grounding rules

- Blackboard facts should come from local DB values, cached content, or tool results.
- Unsupported facts should not be presented as true.
- Inference should be marked as inference.
- Missing data should be acknowledged directly.
- Empty-state behavior should still help the user move forward.

# Workflow

1. Identify the answer path.
   - What response or behavior is being validated?
   - Which tool, DB query, or cached-file path supports it?

2. Trace factual claims.
   - For each Blackboard-facing claim, identify the supporting data source.
   - Separate direct support from interpretation.

3. Check for unsupported certainty.
   - Does the answer sound more certain than the data allows?
   - Is it compressing missing data into a guess?
   - Is it implying current Blackboard state when the repo cannot verify it?

4. Check empty and partial states.
   - What happens when the DB is empty?
   - What happens when cache is missing?
   - What happens when the tool surface only partially supports the request?

5. Improve the response contract if needed.
   - tighten phrasing
   - expose limitations clearly
   - refine tool outputs if the current shape invites misuse

6. Record any true capability gap.
   - If the answer cannot be grounded with the current tool surface, state that explicitly and recommend the smallest meaningful follow-up.

# Verification

Before considering the answer grounded, confirm:

- every factual Blackboard claim is traceable
- unsupported facts are removed or marked as unknown
- inference is distinguishable from fact
- the user still receives a useful response even in low-data situations
- the behavior aligns with the project's grounded-product promise

# Output expectations

When using this skill, produce:

- the answer or behavior being checked
- the supporting repo paths or tool/data sources
- any unsupported or weakly supported claims
- the corrected grounded behavior
- any follow-up capability gaps

Then use `checklist.md` to complete the review.
