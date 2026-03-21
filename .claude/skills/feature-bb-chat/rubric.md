# feature-bb-chat Rubric

Use this rubric after planning or implementing a `bb chat` change.

## 1. Repo reality

- Does the proposed change match the current source tree?
- Does it avoid assuming components exist when they are still only in `PLAN.md`?
- Does it respect the Day 9 foundation and Day 10 priority?

## 2. Correct layer choice

- Was the issue placed in the right layer?
- If the request needed data access, was the tool layer considered first?
- Was prompt-only patching avoided when a tool or schema change would be cleaner?

## 3. Groundedness

- Can every Blackboard-facing factual claim be traced to a tool result, local DB value, or cached file content?
- Are uncertain or unsupported cases stated honestly?
- Is inference separated from fact?

## 4. Tool usability

- Are tool names, outputs, and docstrings clear enough for future chat use?
- Are outputs shaped in a JSON-friendly, predictable way?
- Are empty states still useful to the user?

## 5. Product fit

- Does the change strengthen a terminal-first student workflow?
- Does it help Day 10–11 delivery more than it adds complexity?
- Does it preserve the product promise of practical, grounded help?

## 6. Follow-up clarity

- If the work uncovered a gap that should wait, was it clearly named?
- Are next-step recommendations scoped realistically?
