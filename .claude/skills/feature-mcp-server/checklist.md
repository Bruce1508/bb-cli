# feature-mcp-server Checklist

Use this checklist when reviewing MCP-facing design or implementation work.

## Current-state alignment

- Does the proposal start from the current repository state rather than an imagined full MCP stack?
- Does it treat the current tool layer as the existing AI-facing foundation?
- Does it avoid assuming files or runtime pieces that the repo does not yet contain?

## Tool-surface quality

- Was `bb/tools/queries.py` reviewed before proposing new MCP-only logic?
- Are tool names and docstrings suitable for external AI-facing use?
- Are output shapes predictable and grounded?

## Data-path correctness

- Is the exposed capability backed by real DB, cached-content, or file-backed data?
- Are empty and partial states handled honestly?
- Is the design preserving the product's grounded Blackboard-help promise?

## Sprint fit

- Does the proposal help Day 12 rather than dragging in future-scope ideas?
- Are follow-up improvements clearly named instead of silently folded into the current milestone?

## Architecture discipline

- Is the proposed MCP surface the smallest coherent design?
- Does it minimize duplication with the existing tool layer?
- Does it avoid unnecessary architecture drift from the current repo?
